"""Stage 6: the proof page. One HTML page per run, from the files the other stages left.

    python3 factory/proof.py ZCRED        -> runs/ZCRED/proof.html
"""
import datetime
import hashlib
import html
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

ORACLE_LIMITS = [
    "Batch input proves rules, not display. What a screen shows (names, greyed fields, titles) is only seen through "
    "what it accepts and what it saves.",
    "A success message sent just before the transaction ends never reaches batch input, so for saves the rows are "
    "the evidence, not that message.",
    "Batch input stops at the first error, so retyping after a refusal on the same screen is not tested.",
    "F4 value help does not run under batch input.",
    "Timestamps written by either side are compared as present or empty, not by value.",
    "Messages are compared by their text when they are errors. Warnings and information messages are not compared.",
]


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def transcript_result(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "result":
                return e
    return None


def git_time(path):
    out = subprocess.run(["git", "log", "-1", "--format=%cI %h", "--", path], cwd=ROOT, capture_output=True,
                         text=True).stdout.strip()
    return out


def esc(x):
    return html.escape(str(x))


def diff_words(d):
    if d["what"] == "messages":
        return (f"The old screen said {', '.join(repr(m) for m in d['old']) or 'nothing'}; the new app said "
                f"{', '.join(repr(m) for m in d['new']) or 'nothing'}.")
    if d["what"] == "driver crashed":
        return f"The port's driver failed: {d['error']}"
    parts = []
    if d.get("old_only"):
        parts.append(f"only after the old screen: {json.dumps(d['old_only'], ensure_ascii=False)}")
    if d.get("new_only"):
        parts.append(f"only after the new app: {json.dumps(d['new_only'], ensure_ascii=False)}")
    return f"{d['what']} differ: " + "; ".join(parts)


def main(tcode):
    run = os.path.join(ROOT, "runs", tcode)
    g = load(os.path.join(run, "grade.json"))
    if not g:
        raise SystemExit("grade first: python3 factory/grade.py ZCRED --sealed --out runs/ZCRED/grade.json")
    mut = load(os.path.join(run, "mutants.json"), [])
    chk = load(os.path.join(run, "check.json"), {})
    bundle_path = os.path.join(run, "sealed", "bundle.json")
    digest = hashlib.sha256(open(bundle_path, "rb").read()).hexdigest() if os.path.exists(bundle_path) else "?"
    seal_commit = git_time(f"runs/{tcode}/SEAL.md")
    tests = transcript_result(os.path.join(run, "work", "tests_transcript.jsonl")) or {}
    port = transcript_result(os.path.join(run, "logs", "port_transcript.jsonl")) or {}
    port_start = datetime.datetime.fromtimestamp(
        os.stat(os.path.join(run, "logs", "port_transcript.jsonl")).st_birthtime).astimezone().isoformat(
        timespec="seconds") if os.path.exists(os.path.join(run, "logs", "port_transcript.jsonl")) else "?"
    caught = sum(1 for m in mut if m.get("caught"))
    counted = sum(1 for m in mut if "caught" in m)
    fails = [r for r in g["results"] if not r["pass"]]
    tables = load(os.path.join(run, "extract", "summary.json"), {}).get("tables", [])

    rows = "".join(
        f"<tr><td>{esc(r['id'])}</td><td>{esc(r['intent'])}</td><td>"
        + "<br>".join(esc(diff_words(d)) for d in r["diffs"]) + "</td></tr>" for r in fails)
    mrows = "".join(
        f"<tr><td>{esc(m['change'])}</td><td>{'caught by ' + str(m['failing_cases']) + ' cases' if m.get('caught') else ('not caught' if 'caught' in m else esc(m.get('result', '')))}</td></tr>"
        for m in mut)
    cost = lambda e: f"{e.get('total_cost_usd', 0):.2f} USD, {round(e.get('duration_ms', 0) / 60000)} min" if e else "?"
    limits = "".join(f"<li>{esc(x)}</li>" for x in ORACLE_LIMITS)
    leaks = chk.get("leaks", [])
    reviewed = chk.get("reviewed", [])
    seen = "yes" if leaks and not reviewed else ("no, after review" if leaks else "no")
    review_html = "".join(f"<li>{esc(r['finding'])}. Judged: {esc(r['judgment'])}.</li>" for r in reviewed)
    forbidden = chk.get("forbidden_calls", [])

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Proof Port: {esc(tcode)}</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --line:#e3e0d8; --ok:#1f7a4d; --bad:#b3261e; --card:#ffffff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#151513; --fg:#ecebe6; --muted:#a3a29b; --line:#33322e;
  --ok:#5cc28d; --bad:#f2827b; --card:#1d1d1a; }} }}
body {{ background:var(--bg); color:var(--fg); font:16px/1.55 -apple-system, system-ui, sans-serif; margin:0; }}
main {{ max-width:1100px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:28px; margin:0 0 4px; }} h2 {{ font-size:19px; margin:36px 0 10px; }}
.muted {{ color:var(--muted); }} .score {{ font-size:44px; font-weight:700; margin:18px 0 4px; }}
.ok {{ color:var(--ok); }} .bad {{ color:var(--bad); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.card b {{ display:block; font-size:22px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
td, th {{ text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line); }}
code {{ font-size:13px; word-break:break-all; }}
.wrap {{ overflow-x:auto; }}
</style></head><body><main>
<h1>Proof Port: {esc(tcode)}</h1>
<div class="muted">The old SAP transaction graded its rewrite, on cases sealed before the rewrite began.</div>
<div class="score {'ok' if not fails else 'bad'}">{g['passed']} of {g['cases']}</div>
<div>sealed cases behave the same on the old screen and in the new app (messages and every table row).</div>

<div class="grid" style="margin-top:20px">
 <div class="card"><span class="muted">Mutants caught</span><b>{caught} of {counted}</b>edits that break the port on purpose</div>
 <div class="card"><span class="muted">Sealed</span><b>{esc(seal_commit.split('T')[1][:5] if 'T' in seal_commit else '?')} local</b>commit {esc(seal_commit.split(' ')[-1])}; port started {esc(port_start[11:16])} local</div>
 <div class="card"><span class="muted">Port agent saw the cases</span><b class="{'bad' if seen == 'yes' else 'ok'}">{seen}</b>transcript searched for all {chk.get('sealed_cases', '?')} cases</div>
 <div class="card"><span class="muted">Tables after grading</span><b class="{'ok' if g.get('tables_restored') else 'bad'}">{'as before' if g.get('tables_restored') else 'changed'}</b>every case started from the same data</div>
</div>

<h2>The seal</h2>
<p>SHA-256 of the sealed bundle (cases and the old transaction's answers): <code>{esc(digest)}</code>.
It was committed in <code>runs/{esc(tcode)}/SEAL.md</code> before the port agent started; the bundle itself is published
next to it now. Check: <code>shasum -a 256 runs/{esc(tcode)}/sealed/bundle.json</code>.
{f'<br>{g["drift"]} cases answered differently on the old system than when sealed.' if g.get('drift') else 'The old transaction answered every case as it did when sealed.'}</p>

{f'<h2>What the leak check flagged</h2><ul>{review_html}</ul>' if reviewed else ''}

<h2>Every difference</h2>
{'<p class="ok">None.</p>' if not fails else f'<div class="wrap"><table><tr><th>Case</th><th>What it checks</th><th>Difference</th></tr>{rows}</table></div>'}

<h2>Mutants</h2>
<div class="wrap"><table><tr><th>Change to the port</th><th>Result</th></tr>{mrows or '<tr><td colspan=2>not run</td></tr>'}</table></div>

<h2>What was checked and what wasn't</h2>
<p>Checked, for every case: the error messages (by text) and every row of {', '.join(esc(t) for t in tables)} after the old screen and after the new app, each from the same starting data.
{'Calls into the old transaction found in the port: ' + esc('; '.join(forbidden)) if forbidden else 'No calls into the old transaction were found in the port or its driver.'}</p>
<p>Not checked:</p><ul>{limits}</ul>

<h2>How it ran</h2>
<div class="grid">
 <div class="card"><span class="muted">Test author agent</span><b>{cost(tests)}</b>{g['cases']} cases from the extract alone</div>
 <div class="card"><span class="muted">Port agent</span><b>{cost(port)}</b>RAP object, OData V4 service, driver</div>
 <div class="card"><span class="muted">Grading</span><b>{g['seconds_old']} s + {g['seconds_new']} s</b>old screen, then new app</div>
</div>
<p class="muted">Files: <code>runs/{esc(tcode)}/extract/</code> (what the factory read), <code>sealed/</code> (cases and answers),
<code>port/</code> (the new objects' sources, driver, the agent's report), <code>transcripts/</code> (both agents, cleaned of the machine's tool list),
<code>grade.json</code>, <code>mutants.json</code>.</p>
</main></body></html>"""
    out = os.path.join(run, "proof.html")
    with open(out, "w") as f:
        f.write(page)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1].upper())
