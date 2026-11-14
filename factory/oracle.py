"""Stage 2: the oracle. Replay screen inputs through the old transaction and record what it does.

A case is a list of steps. Each step names a screen, the fields typed into it and the function code pressed:

    {"id": "c001", "steps": [
        {"screen": "0100", "fields": {"GV_KUNNR": "C100"}, "ok": "/00"},
        {"screen": "0200", "fields": {"GV_NEW_LIMIT": "7000"}, "ok": "SAVE"}]}

Values are typed as a user would type them, in the SAP user's own number and date notation. The report on SAP
takes a snapshot of the transaction's tables first, and for every case runs CALL TRANSACTION by batch input,
records the messages and every row of the tables afterwards, then puts the snapshot back. So each case starts from
the same data, and the tables end as they began.

    python3 factory/oracle.py ZCRED cases.json [out.json]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import abap  # noqa: E402
import sap  # noqa: E402

BATCH = 40

TYPES = r"""
TYPES: BEGIN OF ty_base,
         tab  TYPE tabname,
         data TYPE REF TO data,
       END OF ty_base.
TYPES: BEGIN OF ty_msg,
         type   TYPE c LENGTH 1,
         id     TYPE symsgid,
         number TYPE string,
         text   TYPE string,
         screen TYPE string,
       END OF ty_msg.
DATA: gt_bdc  TYPE STANDARD TABLE OF bdcdata,
      gt_msg  TYPE STANDARD TABLE OF bdcmsgcoll,
      gt_base TYPE STANDARD TABLE OF ty_base.
"""

FORMS = r"""
FORM snapshot USING iv_tab TYPE tabname.
  DATA lr TYPE REF TO data.
  FIELD-SYMBOLS <lt> TYPE STANDARD TABLE.
  CREATE DATA lr TYPE STANDARD TABLE OF (iv_tab).
  ASSIGN lr->* TO <lt>.
  SELECT * FROM (iv_tab) INTO TABLE <lt>.
  APPEND VALUE #( tab = iv_tab data = lr ) TO gt_base.
ENDFORM.

FORM restore.
  FIELD-SYMBOLS <lt> TYPE STANDARD TABLE.
  LOOP AT gt_base INTO DATA(ls_base).
    ASSIGN ls_base-data->* TO <lt>.
    DELETE FROM (ls_base-tab).
    INSERT (ls_base-tab) FROM TABLE <lt>.
  ENDLOOP.
  COMMIT WORK AND WAIT.
ENDFORM.

FORM dyn USING iv_prog TYPE csequence iv_dynp TYPE csequence.
  APPEND VALUE #( program = iv_prog dynpro = iv_dynp dynbegin = 'X' ) TO gt_bdc.
ENDFORM.

FORM fld USING iv_name TYPE csequence iv_value TYPE csequence.
  APPEND VALUE #( fnam = iv_name fval = iv_value ) TO gt_bdc.
ENDFORM.

FORM run USING iv_id TYPE csequence.
  DATA: lv_subrc TYPE i,
        lv_json  TYPE string,
        lv_text  TYPE string,
        lv_n     TYPE i,
        lr       TYPE REF TO data.
  FIELD-SYMBOLS <lt> TYPE STANDARD TABLE.
  CLEAR gt_msg.
  DATA(ls_opt) = VALUE ctu_params( dismode = 'N' updmode = 'S' defsize = 'X' ).
  CALL TRANSACTION '{tcode}' USING gt_bdc OPTIONS FROM ls_opt MESSAGES INTO gt_msg.
  lv_subrc = sy-subrc.
  DATA(ls_last) = VALUE ty_msg( type = sy-msgty id = sy-msgid number = sy-msgno ).
  IF sy-msgty IS NOT INITIAL.
    MESSAGE ID sy-msgid TYPE 'I' NUMBER sy-msgno WITH sy-msgv1 sy-msgv2 sy-msgv3 sy-msgv4 INTO ls_last-text.
  ENDIF.
  lv_json = |\{"id":"{ iv_id }","subrc":{ lv_subrc },"last":| && /ui2/cl_json=>serialize( data = ls_last )
    && `,"messages":[`.
  LOOP AT gt_msg INTO DATA(ls_m).
    MESSAGE ID ls_m-msgid TYPE 'I' NUMBER ls_m-msgnr WITH ls_m-msgv1 ls_m-msgv2 ls_m-msgv3 ls_m-msgv4
      INTO lv_text.
    IF lv_n > 0.
      lv_json = lv_json && `,`.
    ENDIF.
    lv_n = lv_n + 1.
    lv_json = lv_json && /ui2/cl_json=>serialize( data = VALUE ty_msg( type = ls_m-msgtyp id = ls_m-msgid
      number = ls_m-msgnr text = lv_text screen = |{ ls_m-dyname } { ls_m-dynumb }| ) ).
  ENDLOOP.
  lv_json = lv_json && `],"tables":{`.
  lv_n = 0.
  LOOP AT gt_base INTO DATA(ls_base).
    CREATE DATA lr TYPE STANDARD TABLE OF (ls_base-tab).
    ASSIGN lr->* TO <lt>.
    SELECT * FROM (ls_base-tab) INTO TABLE <lt>.
    IF lv_n > 0.
      lv_json = lv_json && `,`.
    ENDIF.
    lv_n = lv_n + 1.
    lv_json = lv_json && |"{ ls_base-tab }":| && /ui2/cl_json=>serialize( data = <lt> ).
  ENDLOOP.
  lv_json = lv_json && `}}`.
  PERFORM out USING 'CASE' lv_json.
  PERFORM restore.
  CLEAR gt_bdc.
ENDFORM.
"""


def lit(value):
    return "'" + str(value).replace("'", "''") + "'"


def case_abap(case, program):
    lines = []
    for step in case["steps"]:
        lines.append(f"PERFORM dyn USING {lit(step.get('program', program))} {lit(step['screen'])}.")
        for name, value in step.get("fields", {}).items():
            lines.append(f"PERFORM fld USING {lit(name)} {lit(value)}.")
        lines.append(f"PERFORM fld USING 'BDC_OKCODE' {lit(step.get('ok', '/00'))}.")
    lines.append(f"PERFORM run USING {lit(case['id'])}.")
    return "\n".join(lines)


def load_summary(tcode):
    path = os.path.join(os.path.dirname(__file__), "..", "runs", tcode, "extract", "summary.json")
    with open(path) as f:
        return json.load(f)


def replay(tcode, cases, s=None):
    """Run cases through the old transaction. Returns {case id: {"subrc", "messages", "tables"}}."""
    s = s or sap.Sap()
    summary = load_summary(tcode)
    snapshot = "\n".join(f"PERFORM snapshot USING {lit(t)}." for t in summary["tables"])
    results = {}
    for i in range(0, len(cases), BATCH):
        batch = cases[i:i + BATCH]
        body = snapshot + "\n" + "\n".join(case_abap(c, summary["program"]) for c in batch)
        records = abap.run(s, os.environ.get("ORACLE_REPORT", "ZPP_ORACLE"), body + "\n" + FORMS.replace("{tcode}", summary["tcode"]), types=TYPES)
        for kind, payload in records:
            if kind == "CASE":
                r = json.loads(payload)
                r["messages"] = [{k.lower(): v for k, v in m.items()} for m in r["messages"]]
                r["last"] = {k.lower(): v for k, v in r["last"].items()}
                results[r.pop("id")] = r
        missing = [c["id"] for c in batch if c["id"] not in results]
        if missing:
            raise SystemExit(f"no result for {missing}; see python3 factory/dumps.py")
    return results


if __name__ == "__main__":
    tcode, path = sys.argv[1].upper(), sys.argv[2]
    with open(path) as f:
        cases = json.load(f)
    out = replay(tcode, cases)
    text = json.dumps(out, indent=1, ensure_ascii=False)
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w") as f:
            f.write(text)
    else:
        print(text)
