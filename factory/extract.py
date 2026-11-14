"""Stage 1: extract a custom transaction.

Reads the transaction's program and everything it uses in the customer namespace: source, screens with their fields
and flow logic, GUI status, text pool, messages and dictionary. Objects outside the customer namespace (SAP's own)
are listed by name and never read.

    python3 factory/extract.py ZCRED            -> runs/ZCRED/extract/
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import abap  # noqa: E402
import sap  # noqa: E402

CUSTOMER = re.compile(r"^(Z|Y|SAPMZ|SAPMY|MZ|MY|LZ|LY|SAPLZ|SAPLY|EZ|EY|/[A-Z0-9_]+/)", re.I)

SCREENS_ABAP = r"""
DATA: ls_head TYPE rpy_dyhead,
      lt_cont TYPE dycatt_tab,
      lt_fld  TYPE dyfatc_tab,
      lt_flow TYPE STANDARD TABLE OF rpy_dyflow,
      lt_par  TYPE STANDARD TABLE OF rpy_dypara.
DATA lt_dnum TYPE STANDARD TABLE OF d020s-dnum.
DATA lv_json TYPE string.
SELECT dnum FROM d020s INTO TABLE lt_dnum WHERE prog = '{prog}'.
LOOP AT lt_dnum INTO DATA(lv_dnum).
  CLEAR: ls_head, lt_cont, lt_fld, lt_flow, lt_par.
  CALL FUNCTION 'RPY_DYNPRO_READ'
    EXPORTING progname = '{prog}' dynnr = lv_dnum
    IMPORTING header = ls_head
    TABLES containers = lt_cont fields_to_containers = lt_fld flow_logic = lt_flow params = lt_par
    EXCEPTIONS OTHERS = 1.
  IF sy-subrc = 0.
    lv_json = /ui2/cl_json=>serialize( data = VALUE ty_screen( head = ls_head fields = lt_fld flow = lt_flow ) ).
    PERFORM out USING 'SCREEN' lv_json.
  ENDIF.
ENDLOOP.

DATA lt_tp TYPE STANDARD TABLE OF textpool.
READ TEXTPOOL '{prog}' INTO lt_tp LANGUAGE 'E'.
lv_json = /ui2/cl_json=>serialize( data = lt_tp ).
PERFORM out USING 'TEXTPOOL' lv_json.

"""

SCREENS_TYPES = r"""
TYPES: BEGIN OF ty_screen,
         head   TYPE rpy_dyhead,
         fields TYPE dyfatc_tab,
         flow   TYPE STANDARD TABLE OF rpy_dyflow WITH DEFAULT KEY,
       END OF ty_screen.

"""


def customer(name):
    return bool(CUSTOMER.match(name or ""))


def extract(tcode, out_dir=None):
    s = sap.Sap()
    tcode = tcode.upper()
    out = out_dir or os.path.join(os.path.dirname(__file__), "..", "runs", tcode, "extract")
    os.makedirs(os.path.join(out, "source"), exist_ok=True)

    row = s.sql(f"SELECT PGMNA, DYPNO FROM TSTC WHERE TCODE = '{tcode}'")
    if not row:
        raise SystemExit(f"no transaction {tcode}")
    prog, start = row[0]["PGMNA"], row[0]["DYPNO"]
    if not customer(prog):
        raise SystemExit(f"{tcode} runs {prog}, which is not in the customer namespace")

    # Source: the main program and its customer namespace includes.
    sources = {prog: s.program_source(prog)}
    standard_includes = []
    for r in s.sql(f"SELECT INCLUDE FROM D010INC WHERE MASTER = '{prog}'"):
        inc = r["INCLUDE"]
        if customer(inc):
            sources[inc] = s.include_source(inc)
        else:
            standard_includes.append(inc)
    for name, text in sources.items():
        with open(os.path.join(out, "source", name + ".abap"), "w") as f:
            f.write(text)
    code = "\n".join(sources.values())

    # Screens and text pool, read on the system by a small report. GUI status texts come from RSMPTEXTS.
    records = abap.run(s, "ZPP_EXTRACT", SCREENS_ABAP.format(prog=prog), types=SCREENS_TYPES)
    if not records:
        raise SystemExit("the extract report returned nothing; see the latest short dump (python3 factory/dumps.py)")
    screens = [json.loads(j) for k, j in records if k == "SCREEN"]
    textpool = next((json.loads(j) for k, j in records if k == "TEXTPOOL"), [])
    status = s.sql(f"SELECT OBJ_TYPE, OBJ_CODE, SUB_CODE, TEXTTYPE, TEXT FROM RSMPTEXTS "
                   f"WHERE PROGNAME = '{prog}' AND SPRSL = 'E'")

    # Messages: every customer namespace message class the code names.
    classes = set(m.upper() for m in re.findall(r"MESSAGE-ID\s+(\w+)", code, re.I))
    classes |= set(m.upper() for m in re.findall(r"MESSAGE\s+[AEISWX]\d{3}\((\w+)\)", code, re.I))
    classes |= set(m.upper() for m in re.findall(r"\bID\s+'(\w+)'", code, re.I))
    messages = {}
    for c in sorted(classes):
        if customer(c):
            rows = s.sql(f"SELECT MSGNR, TEXT FROM T100 WHERE SPRSL = 'E' AND ARBGB = '{c}'")
            messages[c] = {r["MSGNR"]: r["TEXT"] for r in rows}
    standard_message_classes = sorted(c for c in classes if not customer(c))

    # Dictionary: customer namespace tables and their fields, data elements, domains and fixed values.
    words = set(w.upper() for w in re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", code))
    words |= {w.split("_", 1)[1] for w in words if w.startswith(("ENQUEUE_", "DEQUEUE_"))}
    for scr in screens:
        for fld in scr.get("FIELDS", []):
            words.update(re.split(r"[-]", fld.get("NAME", "").upper()))
    candidates = sorted(w for w in words if customer(w))
    dictionary = {"tables": {}, "data_elements": {}, "domains": {}, "lock_objects": [], "search_helps": []}
    if candidates:
        names = ", ".join(f"'{w}'" for w in candidates)
        for r in s.sql(f"SELECT TABNAME, TABCLASS FROM DD02L WHERE TABNAME IN ({names}) AND AS4LOCAL = 'A'"):
            t = r["TABNAME"]
            fields = s.sql(f"SELECT FIELDNAME, POSITION, KEYFLAG, ROLLNAME, CHECKTABLE, INTTYPE, DATATYPE, LENG, "
                           f"DECIMALS, NOTNULL FROM DD03L WHERE TABNAME = '{t}' AND AS4LOCAL = 'A' ORDER BY POSITION")
            text = s.sql(f"SELECT DDTEXT FROM DD02T WHERE TABNAME = '{t}' AND DDLANGUAGE = 'E'")
            dictionary["tables"][t] = {"class": r["TABCLASS"], "text": text[0]["DDTEXT"] if text else "",
                                       "fields": fields}
        for r in s.sql(f"SELECT VIEWNAME, ROOTTAB FROM DD25L WHERE VIEWNAME IN ({names}) AND AGGTYPE = 'E' "
                       f"AND AS4LOCAL = 'A'"):
            dictionary["lock_objects"].append({"name": r["VIEWNAME"], "table": r["ROOTTAB"]})
        for r in s.sql(f"SELECT SHLPNAME FROM DD30L WHERE SHLPNAME IN ({names}) AND AS4LOCAL = 'A'"):
            dictionary["search_helps"].append(r["SHLPNAME"])
    rolls = sorted({f["ROLLNAME"] for t in dictionary["tables"].values() for f in t["fields"] if customer(f["ROLLNAME"])})
    if rolls:
        names = ", ".join(f"'{w}'" for w in rolls)
        for r in s.sql(f"SELECT ROLLNAME, DOMNAME, DATATYPE, LENG, DECIMALS FROM DD04L WHERE ROLLNAME IN ({names}) "
                       f"AND AS4LOCAL = 'A'"):
            dictionary["data_elements"][r["ROLLNAME"]] = dict(r)
        for r in s.sql(f"SELECT ROLLNAME, DDTEXT, SCRTEXT_M, SCRTEXT_L FROM DD04T WHERE ROLLNAME IN ({names}) "
                       f"AND DDLANGUAGE = 'E'"):
            dictionary["data_elements"].setdefault(r["ROLLNAME"], {}).update(r)
    doms = sorted({d.get("DOMNAME", "") for d in dictionary["data_elements"].values() if customer(d.get("DOMNAME"))})
    if doms:
        names = ", ".join(f"'{w}'" for w in doms)
        for r in s.sql(f"SELECT DOMNAME, DATATYPE, LENG, DECIMALS, OUTPUTLEN, LOWERCASE, SIGNFLAG, ENTITYTAB "
                       f"FROM DD01L WHERE DOMNAME IN ({names}) AND AS4LOCAL = 'A'"):
            dictionary["domains"][r["DOMNAME"]] = dict(r, values=[])
        for r in s.sql(f"SELECT DOMNAME, VALPOS, DOMVALUE_L, DOMVALUE_H, DDTEXT FROM DD07V WHERE DOMNAME IN ({names}) "
                       f"AND DDLANGUAGE = 'E'"):
            dictionary["domains"].setdefault(r["DOMNAME"], {"values": []})["values"].append(r)

    # SAP's own objects the code uses, by name only.
    standard = {
        "includes": standard_includes,
        "function_modules": sorted({f.upper() for f in re.findall(r"CALL\s+FUNCTION\s+'([^']+)'", code, re.I)
                                    if not customer(f) and not customer(f.upper().split("_", 1)[-1])}),
        "transactions": sorted({t.upper() for t in re.findall(r"(?:CALL|LEAVE\s+TO)\s+TRANSACTION\s+'([^']+)'",
                                                              code, re.I)}),
        "message_classes": standard_message_classes,
        "classes": sorted({c.upper() for c in re.findall(r"\b(CL_\w+|CX_\w+|IF_\w+)\b", code, re.I)}),
    }
    dynamic = [line.strip() for line in code.splitlines()
               if re.search(r"(CALL\s+FUNCTION|SUBMIT|PERFORM|CALL\s+TRANSACTION)\s+\(?[a-z_]\w*\)?\s", line, re.I)
               and not re.search(r"'", line)]

    summary = {"tcode": tcode, "program": prog, "start_screen": start, "sources": sorted(sources),
               "screens": [scr["HEAD"]["SCREEN"] if "HEAD" in scr else "?" for scr in screens],
               "message_classes": sorted(messages), "tables": sorted(dictionary["tables"]),
               "lock_objects": dictionary["lock_objects"], "search_helps": dictionary["search_helps"],
               "standard_objects": standard, "dynamic_calls": dynamic}
    for name, data in [("summary", summary), ("screens", screens), ("status", status), ("textpool", textpool),
                       ("messages", messages), ("dictionary", dictionary)]:
        with open(os.path.join(out, name + ".json"), "w") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
    return summary


if __name__ == "__main__":
    print(json.dumps(extract(sys.argv[1]), indent=1))
