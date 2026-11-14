"""The stage page: the old screen and the new app side by side, and the grade run live, case by case.

Buttons grade the sealed cases (all, or the first 40), break the port on purpose (one mutant from mutate.py) and put
it back from the published source. The old screen is SAP's WebGUI in a frame, signed in by the person at the
keyboard; the new app is factory/app.py, which must already be running (8100 for ZCRED, 8102 for ZMM01).

    python3 factory/stage.py [port]          -> http://127.0.0.1:8200/
"""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import grade  # noqa: E402
import mutate  # noqa: E402
import rap  # noqa: E402
import sap  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBJECTS = {"ZCRED": {"app": "http://127.0.0.1:8100/", "who": "mine, small: one change act on two screens"},
            "ZMM01": {"app": "http://127.0.0.1:8102/",
                      "who": "a stranger's code: trymytoolkit/sap-retail-z-sandbox, MIT, Romain Hecquet"}}
WEBGUI = "/sap/bc/gui/sap/its/webgui?sap-client=001&~transaction={tcode}"
REPO = "https://github.com/alviso/proof-port"
LOCK = threading.Lock()
STATE = {t: {"running": False, "phase": "", "results": [], "total": 0, "error": "", "broken": None,
             "started": 0, "finished": 0} for t in SUBJECTS}


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def behavior_class(tcode):
    return mutate.behavior_classes(tcode)[0]


def published_source(tcode):
    with open(os.path.join(ROOT, "runs", tcode, "port", "src", f"{behavior_class(tcode)}.clas.locals_imp.abap")) as f:
        return f.read()


def same_source(a, b):
    norm = lambda t: [line.rstrip() for line in t.replace("\r", "").strip().splitlines()]
    return norm(a) == norm(b)


def seal_info(tcode):
    run = os.path.join(ROOT, "runs", tcode)
    with open(os.path.join(run, "SEAL.md")) as f:
        text = f.read()
    digest = re.search(r"bundle\.json` \(cases and answers, canonical JSON\): `([0-9a-f]{64})`", text)
    out = subprocess.run(["git", "log", "-1", "--format=%h %cI", "--", f"runs/{tcode}/SEAL.md"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip().split()
    log = os.path.join(run, "logs", "port_transcript.jsonl")
    port_start = time.strftime("%H:%M", time.localtime(os.stat(log).st_birthtime)) if os.path.exists(log) else "?"
    g = load(os.path.join(run, "grade.json"), {})
    mut = load(os.path.join(run, "mutants.json"), [])
    return {"digest": digest.group(1) if digest else "?", "commit": out[0] if out else "?",
            "sealed_at": out[1][11:16] if len(out) > 1 else "?", "port_started": port_start,
            "last": {"passed": g.get("passed"), "cases": g.get("cases")},
            "mutants": {"caught": sum(1 for m in mut if m.get("caught")), "of": sum(1 for m in mut if "caught" in m)},
            "proof": f"{REPO}/blob/main/runs/{tcode}/proof.html", "seal_commit": f"{REPO}/commit/{out[0]}" if out else REPO}


def run_grade(tcode, limit):
    st = STATE[tcode]
    try:
        with open(os.path.join(ROOT, "runs", tcode, "sealed", "bundle.json")) as f:
            cases = json.load(f)["cases"]
        if limit:
            cases = cases[:limit]
        st.update(total=len(cases), results=[], phase="asking the old screen", error="", started=time.time())

        def on_case(r):
            st["phase"] = "the new app"
            st["results"].append({"id": r["id"], "intent": r["intent"], "pass": r["pass"],
                                  "diffs": [describe(d) for d in r["diffs"]]})

        grade.grade(tcode, cases, "ZPP_RESTORE_S", "ZPP_ORACLE_S", sap.Sap(), on_case=on_case)
        st["phase"] = "done"
    except Exception as e:  # shown on the page, not swallowed
        st["error"] = f"{type(e).__name__}: {e}"
        st["phase"] = "failed"
    finally:
        st["running"] = False
        st["finished"] = time.time()


def describe(d):
    if d["what"] == "messages":
        return f"old said {d['old'] or 'nothing'}, new said {d['new'] or 'nothing'}"
    if d["what"] == "driver crashed":
        return d["error"]
    return f"{d['what']} differ"


def break_port(tcode):
    s = sap.Sap()
    cls = behavior_class(tcode)
    original = published_source(tcode)
    found = list(mutate.mutants(original))
    desc, mutated = found[1] if len(found) > 1 else found[0]
    rap.put(s, "CLAS", cls, mutated, part="implementations")
    errs = [m for m in rap.activate(s, [("CLAS", cls)]) if m.startswith(("E", "A"))]
    if errs:
        rap.put(s, "CLAS", cls, original, part="implementations")
        rap.activate(s, [("CLAS", cls)])
        raise RuntimeError("the break did not activate: " + "; ".join(errs[:2]))
    STATE[tcode]["broken"] = desc


def fix_port(tcode):
    s = sap.Sap()
    cls = behavior_class(tcode)
    rap.put(s, "CLAS", cls, published_source(tcode), part="implementations")
    errs = [m for m in rap.activate(s, [("CLAS", cls)]) if m.startswith(("E", "A"))]
    if errs:
        raise RuntimeError("putting it back did not activate: " + "; ".join(errs[:2]))
    STATE[tcode]["broken"] = None


def check_broken(tcode):
    active = rap.get(sap.Sap(), "CLAS", behavior_class(tcode), "implementations")
    if same_source(active, published_source(tcode)):
        STATE[tcode]["broken"] = None
    elif not STATE[tcode]["broken"]:
        STATE[tcode]["broken"] = "the active code differs from the published source"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        tcode = q.get("t", "ZCRED").upper()
        if url.path == "/":
            with open(os.path.join(os.path.dirname(__file__), "stage.html")) as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if tcode not in SUBJECTS:
            return self.send(404, json.dumps({"error": "unknown subject"}))
        if url.path == "/api/state":
            try:
                check_broken(tcode)
            except Exception as e:
                STATE[tcode]["error"] = f"could not read the port's code: {e}"
            info = dict(seal_info(tcode), subject=tcode, who=SUBJECTS[tcode]["who"], app=SUBJECTS[tcode]["app"],
                        webgui=sap.Sap().url + WEBGUI.format(tcode=tcode), broken=STATE[tcode]["broken"])
            return self.send(200, json.dumps(info))
        if url.path == "/api/progress":
            st = STATE[tcode]
            return self.send(200, json.dumps({k: st[k] for k in ("running", "phase", "results", "total", "error",
                                                                 "broken", "started", "finished")}))
        return self.send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        tcode = q.get("t", "ZCRED").upper()
        if tcode not in SUBJECTS:
            return self.send(404, json.dumps({"error": "unknown subject"}))
        with LOCK:
            if any(st["running"] for st in STATE.values()):
                return self.send(409, json.dumps({"error": "a grade is already running"}))
            try:
                if url.path == "/api/grade":
                    STATE[tcode]["running"] = True
                    threading.Thread(target=run_grade, args=(tcode, int(q.get("n", 0))), daemon=True).start()
                    return self.send(200, json.dumps({"ok": True}))
                if url.path == "/api/break":
                    break_port(tcode)
                    return self.send(200, json.dumps({"broken": STATE[tcode]["broken"]}))
                if url.path == "/api/fix":
                    fix_port(tcode)
                    return self.send(200, json.dumps({"broken": None}))
            except Exception as e:
                return self.send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return self.send(404, json.dumps({"error": "not found"}))


def main(port=8200):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"stage page on http://127.0.0.1:{port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8200)
