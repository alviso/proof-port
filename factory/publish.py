"""After grading: publish a run, cleaned.

Copies both agents' transcripts into runs/<TCODE>/transcripts/ without what describes the machine they ran on (the
session's start event lists every tool and connector of the person running it, and paths name their home folder),
then refuses to go on if any file to be published holds a password from the env files or a host address. Then commits
and pushes the sealed bundle, the port, the transcripts, the grade, the mutants, the leak check and the proof page.

    python3 factory/publish.py ZCRED [--no-push]
"""
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import sap  # noqa: E402

HOME = os.path.expanduser("~")
ENV_FILES = ["~/.config/evolve/a4h.env", "~/.config/evolve/a4h_agent.env"]
KEEP_INIT = ("type", "subtype", "model", "permissionMode", "claude_code_version")


def clean_event(e):
    if e.get("type") == "system" and e.get("subtype") == "init":
        return {k: e[k] for k in KEEP_INIT if k in e}
    return scrub(e)


def scrub(value):
    """Clean every string inside an event, leaving its structure alone."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        value = value.replace(HOME, "~")
        return re.sub(r"/private/tmp/claude-\d+/[^\s\"'\\]*", "<scratch>", value)
    return value


def clean_transcript(src, dst):
    with open(src) as f, open(dst, "w") as out:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            out.write(json.dumps(clean_event(e), ensure_ascii=False) + "\n")


def secrets():
    values = []
    for path in ENV_FILES:
        try:
            values.append(sap.load_env(path)["A4H_PASSWORD"])
        except (OSError, KeyError):
            pass
    return [v for v in values if len(v) >= 6]


def scan(paths):
    bad = []
    pw = secrets()
    host = re.compile(r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b")
    for path in paths:
        with open(path, errors="replace") as f:
            text = f.read()
        if any(p in text for p in pw):
            bad.append(f"{path}: holds a password")
        for m in host.finditer(text):
            if re.match(r"\d+\.\d+\.\d+\.\d+\.\d", text[m.start():m.end() + 2]):  # a version number
                continue
            if all(int(part) <= 255 for part in m.group(0).split(".")):  # 12.345.678.901 is a number typed in SAP
                bad.append(f"{path}: address {m.group(0)}")
                break
        if "A4H_PASSWORD=" in text:
            bad.append(f"{path}: an env line")
    return bad


def main(tcode, push=True):
    run = os.path.join(ROOT, "runs", tcode)
    out = os.path.join(run, "transcripts")
    os.makedirs(out, exist_ok=True)
    for src, name in [(os.path.join(run, "work", "tests_transcript.jsonl"), "tests.jsonl"),
                      (os.path.join(run, "logs", "port_transcript.jsonl"), "port.jsonl")]:
        if os.path.exists(src):
            clean_transcript(src, os.path.join(out, name))
    paths = [p for p in glob.glob(os.path.join(run, "**", "*"), recursive=True)
             if os.path.isfile(p) and "/logs/" not in p and "/work/" not in p]
    bad = scan(paths)
    if bad:
        raise SystemExit("not published:\n" + "\n".join(bad))
    rels = [os.path.relpath(p, ROOT) for p in paths]
    subprocess.run(["git", "add", "-f", "--"] + rels, cwd=ROOT, check=True)
    msg = (f"Publish {tcode}: sealed bundle, port, transcripts, grade, mutants, proof page\n\n"
           "Transcripts are cleaned of the machine's tool list and home paths.\n\n"
           "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    if push:
        subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    print(f"published {len(rels)} files")


if __name__ == "__main__":
    main(sys.argv[1].upper(), push="--no-push" not in sys.argv)
