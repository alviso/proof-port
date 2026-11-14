"""Stage 4: have a second agent port the transaction, walled off from the sealed cases.

Before it starts, the sealed cases and the test author's transcript are moved out of the project into a vault
folder, and the agent's permissions deny reading them anyway. The agent signs in to SAP as its own user (SAP_ENV),
may only create objects named RAP_PREFIX..., and may write only inside runs/<TCODE>/port/. Its transcript goes to
runs/<TCODE>/logs/port_transcript.jsonl. Afterwards check.py searches that transcript and the port for every case.

    python3 factory/port.py ZCRED ZPP_CR_ [model]
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import vault  # noqa: E402


def main(tcode, prefix, model="opus"):
    with open(os.path.join(ROOT, "runs", tcode, "extract", "summary.json")) as f:
        summary = json.load(f)
    with open(os.path.join(ROOT, "factory", "briefs", "port.md")) as f:
        brief = (f.read().replace("{TCODE}", tcode).replace("{PROG}", summary["program"])
                 .replace("{PREFIX}", prefix))
    brief += "\nName your own cases p001, p002, ... so they are easy to tell apart from anyone else's.\n"
    vault.lock(tcode)
    port = os.path.join(ROOT, "runs", tcode, "port")
    os.makedirs(os.path.join(port, "src"), exist_ok=True)
    logs = os.path.join(ROOT, "runs", tcode, "logs")
    os.makedirs(logs, exist_ok=True)
    allowed = ",".join([
        "Read", "Glob", "Grep",
        f"Write(runs/{tcode}/port/**)", f"Edit(runs/{tcode}/port/**)",
        "Bash(python3 factory/rap.py *)",
        f"Bash(python3 factory/oracle.py {tcode} *)",
        f"Bash(python3 factory/grade.py {tcode} *)",
        "Bash(ls *)", "Bash(wc *)", "Bash(mkdir -p runs/*)",
    ])
    denied = ",".join(["Read(runs/*/sealed/**)", "Read(runs/*/work/**)", "Read(runs/*/logs/**)",
                       "Read(~/.config/**)", "Bash(pkill *)"])
    cmd = ["claude", "-p", brief, "--model", model, "--allowedTools", allowed, "--disallowedTools", denied,
           "--output-format", "stream-json", "--verbose", "--max-turns", "500"]
    env = dict(os.environ, SAP_ENV=os.path.expanduser("~/.config/evolve/a4h_agent.env"), RAP_PREFIX=prefix,
               ORACLE_REPORT="ZPP_ORACLE_P")
    log = os.path.join(logs, "port_transcript.jsonl")
    with open(log, "w") as out:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env)
    with open(log) as f:
        for line in f:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                print(f"cost {event.get('total_cost_usd')} USD, {event.get('num_turns')} turns, "
                      f"{round(event.get('duration_ms', 0) / 60000, 1)} min")
                print(event.get("result", ""))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].upper(), sys.argv[2].upper(), *sys.argv[3:]))
