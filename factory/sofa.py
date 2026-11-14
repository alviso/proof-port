"""After a run: record it in 8090's Software Factory (knowledge, requirements, blueprint, work order, test results).

Runs Claude Code headless with the brief in factory/briefs/sofa.md and only the Software Factory MCP server of the
Proof Port project. Its transcript goes to runs/<TCODE>/logs/sofa_transcript.jsonl.

    python3 factory/sofa.py ZCRED [model]
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER = "software-factory-proof-port"


def main(tcode, model="sonnet"):
    with open(os.path.join(ROOT, "factory", "briefs", "sofa.md")) as f:
        brief = f.read().replace("{TCODE}", tcode)
    allowed = ",".join(["Read", "Glob", "Grep", f"mcp__{SERVER}", "Bash(curl *)", "Bash(ls *)", "Bash(wc *)"])
    cmd = ["claude", "-p", brief, "--model", model, "--allowedTools", allowed,
           "--output-format", "stream-json", "--verbose", "--max-turns", "300"]
    logs = os.path.join(ROOT, "runs", tcode, "logs")
    os.makedirs(logs, exist_ok=True)
    log = os.path.join(logs, "sofa_transcript.jsonl")
    with open(log, "w") as out:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
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
    sys.exit(main(sys.argv[1].upper(), *sys.argv[2:]))
