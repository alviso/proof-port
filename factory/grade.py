"""Stage 5: grade the port against the old transaction.

Every case goes through the old screen (the oracle, run fresh) and through the new service (the port's driver),
each starting from the same data. Then the error messages and every table row are compared.

    python3 factory/grade.py ZCRED CASES.json [--out report.json]      cases of your own
    python3 factory/grade.py ZCRED --sealed [--out report.json]         the sealed cases (factory only)

The driver is runs/<TCODE>/port/driver.py with a function run(client, steps). It gets an odata.Client for the new
service (runs/<TCODE>/port/service.json names the service root) and the steps of one case, and does what a user of
the new app would do to achieve the same. It returns nothing; the grader reads the messages from the client's calls
and the rows from the database.
"""
import hashlib
import importlib.util
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import abap  # noqa: E402
import odata  # noqa: E402
import oracle  # noqa: E402
import sap  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VOLATILE_ROLLS = {"TIMESTAMP", "TIMESTAMPL", "TZNTSTMPS", "TZNTSTMPL", "SYUZEIT", "UZEIT"}
STOPPED = ("00", "344")  # batch input: the steps ran out on a screen, so the user stopped there


def load_json(path):
    with open(path) as f:
        return json.load(f)


def volatile_fields(tcode):
    d = load_json(os.path.join(ROOT, "runs", tcode, "extract", "dictionary.json"))
    out = {}
    for table, t in d["tables"].items():
        out[table] = {f["FIELDNAME"] for f in t["fields"]
                      if f["ROLLNAME"] in VOLATILE_ROLLS or f["DATATYPE"] == "TIMS"
                      # a time stamp typed directly, without a data element: DEC 15,0 or DEC 21,7
                      or (f["DATATYPE"] == "DEC" and (int(f["LENG"]), int(f["DECIMALS"])) in ((15, 0), (21, 7)))}
    return out


def table_fields(tcode):
    d = load_json(os.path.join(ROOT, "runs", tcode, "extract", "dictionary.json"))
    return {t: [f["FIELDNAME"] for f in v["fields"] if not f["FIELDNAME"].startswith(".")] for t, v in
            d["tables"].items() if v["class"] == "TRANSP"}


def read_tables(s, fields):
    return {t: s.sql(f"SELECT {', '.join(fl)} FROM {t}") for t, fl in fields.items()}


def lit(v):
    return "'" + str(v).replace("'", "''") + "'"


def after_report(baseline, fields):
    """One report per case: write every row as the case left it, then put the baseline back. Reading through the
    data preview instead runs out of generated programs in one session after a few cases."""
    lines = ["DATA lv_json TYPE string."]
    for table in baseline:
        t = table.lower()
        lines.append(f"DATA lt_{t}_now TYPE STANDARD TABLE OF {t}.")
        lines.append(f"SELECT * FROM {t} INTO TABLE lt_{t}_now.")
        lines.append(f"lv_json = /ui2/cl_json=>serialize( data = lt_{t}_now ).")
        lines.append(f"PERFORM out USING '{table}' lv_json.")
    return "\n".join(lines) + "\n" + restore_report(baseline, fields)


def restore_report(baseline, fields):
    lines = []
    for table, rows in baseline.items():
        lines.append(f"DATA lt_{table.lower()} TYPE STANDARD TABLE OF {table.lower()}.")
        for r in rows:
            assigns = " ".join(f"{f.lower()} = {lit(r[f])}" for f in fields[table] if f != "MANDT" and r[f] != "")
            lines.append(f"APPEND VALUE {table.lower()}( {assigns} ) TO lt_{table.lower()}.")
        lines.append(f"DELETE FROM {table.lower()}.")
        lines.append(f"INSERT {table.lower()} FROM TABLE lt_{table.lower()}.")
    lines.append("COMMIT WORK AND WAIT.")
    return "\n".join(lines)


def norm(value):
    """Compare numbers as numbers: the oracle writes 7000.00 as 7000.0, the database as '7000.00'."""
    if isinstance(value, (int, float)):
        return repr(float(value))
    text = str(value).strip()
    try:
        if text and any(c.isdigit() for c in text) and text.replace(".", "", 1).replace("-", "", 1).isdigit():
            return repr(float(text))
    except ValueError:
        pass
    return text


def normalise_rows(rows, volatile):
    out = []
    for r in rows:
        row = {}
        for k, v in r.items():
            if k == "MANDT":
                continue
            row[k] = ("<set>" if norm(v) not in ("", "0.0") else "<empty>") if k in volatile else norm(v)
        out.append(json.dumps(row, sort_keys=True))
    return sorted(out)


def errors(messages):
    out = []
    for m in messages:
        if (m.get("id"), str(m.get("number"))) == STOPPED:
            continue
        if m.get("type") in ("E", "A", "X"):
            out.append(m.get("text", "").strip())
    return sorted(set(out))


def compare(old, new, vol):
    diffs = []
    old_err, new_err = errors(old["messages"]), errors(new["messages"])
    if old_err != new_err:
        diffs.append({"what": "messages", "old": old_err, "new": new_err})
    for table in old["tables"]:
        a = normalise_rows(old["tables"][table], vol.get(table, set()))
        b = normalise_rows(new["tables"].get(table, []), vol.get(table, set()))
        if a != b:
            only_old = [json.loads(x) for x in a if x not in b]
            only_new = [json.loads(x) for x in b if x not in a]
            diffs.append({"what": f"rows of {table}", "old_only": only_old, "new_only": only_new})
    return diffs


def load_driver(tcode):
    path = os.path.join(ROOT, "runs", tcode, "port", "driver.py")
    spec = importlib.util.spec_from_file_location("driver", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RecordingClient(odata.Client):
    """Keeps every message the service sent during one case."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seen = []

    def call(self, method, path, data=None, headers=None):
        r = super().call(method, path, data, headers)
        self.seen.extend(r.messages)
        return r

    def ui(self, type_, text):
        r = super().ui(type_, text)
        self.seen.append({"type": type_, "text": text, "from": "ui"})
        return r


def grade(tcode, cases, report_name="ZPP_RESTORE", oracle_report="ZPP_ORACLE_G", s=None, sealed_answers=None,
          on_case=None):
    """on_case, if given, is called with each case's result as soon as it is graded (the stage page uses it)."""
    s = s or sap.Sap()
    # One set of helper reports per transaction, so runs for different transactions can go at the same time.
    report_name, oracle_report = f"{report_name}_{tcode}"[:30], f"{oracle_report}_{tcode}"[:30]
    fields = table_fields(tcode)
    vol = volatile_fields(tcode)
    os.environ["ORACLE_REPORT"] = oracle_report
    old = oracle.replay(tcode, cases, s)
    baseline = read_tables(s, fields)
    s.write_program(report_name, abap.build(report_name, after_report(baseline, fields)))
    service = load_json(os.path.join(ROOT, "runs", tcode, "port", "service.json"))
    driver = load_driver(tcode)
    results = []
    for case in cases:
        client = RecordingClient(service["root"], s)
        crash = None
        try:
            driver.run(client, case["steps"])
        except Exception as e:  # the driver failing is a result too
            crash = f"{type(e).__name__}: {e}"
        rows = {k: json.loads(v) for k, v in abap.parse(s.run_program(report_name)) if k in fields}
        new = {"messages": client.seen, "tables": rows}
        diffs = compare(old[case["id"]], new, vol)
        if crash:
            diffs.insert(0, {"what": "driver crashed", "error": crash})
        drift = None
        if sealed_answers is not None:
            sealed_old = sealed_answers.get(case["id"])
            if sealed_old is None or compare(sealed_old, old[case["id"]], vol):
                drift = "the old transaction answered differently than when the cases were sealed"
        results.append({"id": case["id"], "intent": case.get("intent", ""), "pass": not diffs, "diffs": diffs,
                        "old_messages": errors(old[case["id"]]["messages"]), "new_messages": client.seen,
                        "drift": drift})
        if on_case:
            on_case(results[-1])
    after = read_tables(s, fields)
    clean = all(normalise_rows(after[t], vol[t]) == normalise_rows(baseline[t], vol[t]) for t in fields)
    passed = sum(r["pass"] for r in results)
    return {"tcode": tcode, "cases": len(cases), "passed": passed, "failed": len(cases) - passed,
            "drift": sum(1 for r in results if r["drift"]), "tables_restored": clean,
            "results": results}


def main(argv):
    tcode = argv[0].upper()
    out = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    sealed_answers = None
    if "--sealed" in argv:
        bundle_path = os.path.join(ROOT, "runs", tcode, "sealed", "bundle.json")
        with open(bundle_path, "rb") as f:
            raw = f.read()
        bundle = json.loads(raw)
        cases, sealed_answers = bundle["cases"], bundle["answers"]
        print(f"sealed bundle sha256 {hashlib.sha256(raw).hexdigest()}")
        report_name, oracle_report = "ZPP_RESTORE", "ZPP_ORACLE_G"
    else:
        cases = load_json(argv[1])
        report_name, oracle_report = "ZPP_RESTORE_P", "ZPP_ORACLE_P"
    report = grade(tcode, cases, report_name, oracle_report, sealed_answers=sealed_answers)
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if out:
        with open(out, "w") as f:
            f.write(text)
    print(f"{report['passed']} of {report['cases']} cases behave the same; tables restored: "
          f"{report['tables_restored']}; drift: {report['drift']}")
    for r in report["results"]:
        if not r["pass"]:
            print(f"- {r['id']} {r['intent']}")
            for d in r["diffs"]:
                print(f"    {json.dumps(d, ensure_ascii=False)[:400]}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
