"""After the port: did the port agent see the sealed cases?

Looks at what the agent did and wrote, not at what the factory showed it: every tool call it made, every message it
wrote, and every file in its port folder. Flags any tool call that touches the sealed cases, the test author's work
or the vault; any sealed case intent it repeats; and any sealed case id it writes that the public factory files don't
already contain as an example. Also checks the new objects and the driver for calls into the old transaction.

    python3 factory/check.py ZCRED
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import vault  # noqa: E402

CASE_ID = re.compile(r"(?<![\w-])c\d{3}(?![\w-])")
AS_ID = re.compile(r'"id\\?"\s*:\s*\\?"(c\d{3})\\?"')  # used as a case's id, in JSON or in JSON inside JSON
ACCESS_TOOLS = ("Read", "Glob", "Grep", "Bash", "Edit", "NotebookEdit")
TOUCH = re.compile(r"sealed|/work\b|/work/|proof-port-vault|bundle\.json|tests_transcript", re.I)
FORBIDDEN_ABAP = [r"CALL\s+TRANSACTION", r"\bSUBMIT\b", r"PERFORM\s+\w+\s+IN\s+PROGRAM", r"BDCDATA", r"SAPMZ\w+"]
FORBIDDEN_DRIVER = [r"^\s*(import|from)\s+(sap|abap|oracle|grade)\b", r"urllib\.request", r"http\.client", r"\bsocket\b",
                    r"\brequests\b", r"subprocess", r"\bopen\(", r"run_program", r"run_abap", r"\.sql\("]


def sealed_bundle(tcode):
    for base in (os.path.join(ROOT, "runs", tcode, "sealed"), os.path.join(vault.VAULT, tcode, "sealed")):
        path = os.path.join(base, "bundle.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    raise SystemExit("no sealed bundle found")


def agent_output(tcode):
    """(where, text) for everything the agent produced: tool inputs, its own words, its files."""
    out = []
    with open(os.path.join(ROOT, "runs", tcode, "logs", "port_transcript.jsonl")) as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") != "assistant":
                continue
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    out.append((f"tool call {c['name']}", json.dumps(c["input"], ensure_ascii=False)))
                elif c.get("type") == "text":
                    out.append(("agent's words", c["text"]))
    port = os.path.join(ROOT, "runs", tcode, "port")
    for dirpath, _, files in os.walk(port):
        for name in files:
            path = os.path.join(dirpath, name)
            with open(path, errors="replace") as f:
                out.append((os.path.relpath(path, ROOT), f.read()))
    return out


def public_ids():
    ids = set()
    for dirpath, _, files in os.walk(os.path.join(ROOT, "factory")):
        for name in files:
            if name.endswith((".py", ".md")):
                with open(os.path.join(dirpath, name)) as f:
                    ids |= set(CASE_ID.findall(f.read()))
    return ids


def main(tcode):
    bundle = sealed_bundle(tcode)
    sealed_ids = {c["id"] for c in bundle["cases"]}
    intents = [c["intent"] for c in bundle["cases"] if len(c.get("intent", "")) > 30]
    examples = public_ids()
    leaks, notes = [], []
    for where, text in agent_output(tcode):
        if where.startswith("tool call") and where.split()[-1] in ACCESS_TOOLS:
            for m in TOUCH.finditer(text):
                excluded = "-not -path" in text[max(0, m.start() - 16):m.start()]
                (notes if excluded else leaks).append(f"{where} {'excludes' if excluded else 'touches'} "
                                                     f"{m.group(0)}: {text[:160]}")
        ids = sorted((set(AS_ID.findall(text)) & sealed_ids) - examples)
        if ids:
            leaks.append(f"{where}: sealed case ids {ids[:10]}")
        for intent in intents:
            if intent in text:
                leaks.append(f"{where}: repeats the intent of a sealed case: {intent[:80]}")
    calls = []
    src = os.path.join(ROOT, "runs", tcode, "port", "src")
    for name in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        with open(os.path.join(src, name), errors="replace") as f:
            text = f.read()
        calls += [f"{name}: {p}" for p in FORBIDDEN_ABAP if re.search(p, text, re.I)]
    driver = os.path.join(ROOT, "runs", tcode, "port", "driver.py")
    if os.path.exists(driver):
        with open(driver) as f:
            text = f.read()
        calls += [f"driver.py: {p}" for p in FORBIDDEN_DRIVER if re.search(p, text, re.M)]
    result = {"sealed_cases": len(sealed_ids), "leaks": leaks, "notes": notes, "forbidden_calls": calls}
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return result


if __name__ == "__main__":
    r = main(sys.argv[1].upper())
    sys.exit(1 if r["leaks"] or r["forbidden_calls"] else 0)
