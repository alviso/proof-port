"""Stage 3a: have an agent write test cases from the extract alone.

Runs Claude Code headless with the brief in factory/briefs/tests.md. The agent may read the extract, run the oracle
and write only inside runs/<TCODE>/sealed/. Its transcript goes to runs/<TCODE>/work/tests_transcript.jsonl.

    python3 factory/tests.py ZCRED [model]
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main(tcode, model="opus"):
    with open(os.path.join(ROOT, "runs", tcode, "extract", "summary.json")) as f:
        summary = json.load(f)
    with open(os.path.join(ROOT, "factory", "briefs", "tests.md")) as f:
        brief = f.read().replace("{TCODE}", tcode).replace("{PROG}", summary["program"])
    os.makedirs(os.path.join(ROOT, "runs", tcode, "sealed"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "runs", tcode, "work"), exist_ok=True)
    allowed = ",".join([
        "Read", "Glob", "Grep",
        f"Write(runs/{tcode}/sealed/**)", f"Edit(runs/{tcode}/sealed/**)",
        f"Bash(python3 factory/oracle.py {tcode} *)",
        "Bash(python3 -c:*)", "Bash(ls:*)", "Bash(wc:*)",
    ])
    cmd = ["claude", "-p", brief, "--model", model, "--allowedTools", allowed,
           "--output-format", "stream-json", "--verbose", "--max-turns", "200"]
    log = os.path.join(ROOT, "runs", tcode, "work", "tests_transcript.jsonl")
    with open(log, "w") as out:
        env = dict(os.environ, ORACLE_REPORT="ZPP_ORACLE_T")
        proc = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env)
    final = ""
    with open(log) as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                final = event.get("result", "")
                print(f"cost {event.get('total_cost_usd')} USD, {event.get('num_turns')} turns, "
                      f"{round(event.get('duration_ms', 0) / 60000, 1)} min")
    print(final)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].upper(), *sys.argv[2:]))
