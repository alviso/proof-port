"""After the port: did the port agent see the sealed cases?

Searches the port agent's transcript and everything it wrote for the sealed cases' ids, their intents, the vault
path and the bundle's name, and checks the new objects for calls into the old transaction.

    python3 factory/check.py ZCRED
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import vault  # noqa: E402

FORBIDDEN_ABAP = [r"CALL\s+TRANSACTION", r"\bSUBMIT\b", r"PERFORM\s+\w+\s+IN\s+PROGRAM", r"BDCDATA", r"SAPMZ\w+"]


def sealed_bundle(tcode):
    for base in (os.path.join(ROOT, "runs", tcode, "sealed"), os.path.join(vault.VAULT, tcode, "sealed")):
        path = os.path.join(base, "bundle.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    raise SystemExit("no sealed bundle found")


def texts(tcode):
    out = {}
    log = os.path.join(ROOT, "runs", tcode, "logs", "port_transcript.jsonl")
    with open(log) as f:
        out["transcript"] = f.read()
    port = os.path.join(ROOT, "runs", tcode, "port")
    for dirpath, _, files in os.walk(port):
        for name in files:
            path = os.path.join(dirpath, name)
            with open(path, errors="replace") as f:
                out[os.path.relpath(path, ROOT)] = f.read()
    return out


def main(tcode):
    bundle = sealed_bundle(tcode)
    sealed_ids = {c["id"] for c in bundle["cases"]}
    intents = [c["intent"] for c in bundle["cases"] if len(c.get("intent", "")) > 30]
    found = []
    for where, text in texts(tcode).items():
        hits = sorted(set(re.findall(r"\bc\d{3}\b", text)) & sealed_ids)
        if hits:
            found.append(f"{where}: case ids {hits[:10]}{' ...' if len(hits) > 10 else ''}")
        for marker in ("bundle.json", "proof-port-vault", "/sealed/", "tests_transcript"):
            if marker in text:
                found.append(f"{where}: mentions {marker}")
        for intent in intents:
            if intent in text:
                found.append(f"{where}: contains the intent of a sealed case: {intent[:80]}")
    calls = []
    port_src = os.path.join(ROOT, "runs", tcode, "port", "src")
    for name in sorted(os.listdir(port_src)) if os.path.isdir(port_src) else []:
        with open(os.path.join(port_src, name), errors="replace") as f:
            src = f.read()
        for pattern in FORBIDDEN_ABAP:
            if re.search(pattern, src, re.I):
                calls.append(f"{name}: {pattern}")
    driver = os.path.join(ROOT, "runs", tcode, "port", "driver.py")
    if os.path.exists(driver):
        with open(driver) as f:
            d = f.read()
        for pattern in (r"\bsap\.", r"\bsql\(", r"run_program", r"run_abap", r"oracle", r"open\(", r"subprocess",
                        r"urllib", r"requests"):
            if re.search(pattern, d):
                calls.append(f"driver.py uses {pattern}")
    result = {"sealed_cases": len(sealed_ids), "leaks": found, "forbidden_calls": calls}
    print(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    r = main(sys.argv[1].upper())
    sys.exit(1 if r["leaks"] or r["forbidden_calls"] else 0)
