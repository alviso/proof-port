"""Stage 3b: seal the test cases before the port starts.

Asks the oracle for every case, writes runs/<TCODE>/sealed/bundle.json (cases and the old transaction's answers, as
canonical JSON) and commits its SHA-256 in runs/<TCODE>/SEAL.md, pushed to the public repo. The sealed folder itself
stays out of git until grading is done, so the history shows the tests existed before the code they judge.

    python3 factory/seal.py ZCRED [--no-push]
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import oracle  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check(cases):
    problems = []
    ids = [c.get("id") for c in cases]
    if len(set(ids)) != len(ids):
        problems.append("duplicate ids")
    for c in cases:
        if not c.get("steps"):
            problems.append(f"{c.get('id')}: no steps")
        for st in c.get("steps", []):
            if "screen" not in st:
                problems.append(f"{c.get('id')}: a step without a screen")
            for name, value in st.get("fields", {}).items():
                if len(str(value)) > 132:
                    problems.append(f"{c.get('id')}: {name} is longer than batch input takes (132)")
    return problems


def main(tcode, push=True):
    sealed = os.path.join(ROOT, "runs", tcode, "sealed")
    with open(os.path.join(sealed, "cases.json")) as f:
        cases = json.load(f)
    problems = check(cases)
    if problems:
        raise SystemExit("not sealed: " + "; ".join(problems))
    os.environ["ORACLE_REPORT"] = "ZPP_ORACLE_S"
    answers = oracle.replay(tcode, cases)
    bundle = {"tcode": tcode, "cases": cases, "answers": answers}
    data = canonical(bundle)
    with open(os.path.join(sealed, "bundle.json"), "wb") as f:
        f.write(data)
    digest = hashlib.sha256(data).hexdigest()
    cases_digest = hashlib.sha256(canonical(cases)).hexdigest()
    when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    errors = sum(1 for a in answers.values() if any(m["type"] in "EAX" for m in a["messages"]))
    seal = f"""# {tcode}: sealed test cases

Sealed {when}, before the port started. The cases were written by an agent from the extract alone, and every
expected result is what the old transaction did when the oracle ran the case.

- Cases: {len(cases)} ({errors} of them end in an error message from the old transaction)
- SHA-256 of `runs/{tcode}/sealed/bundle.json` (cases and answers, canonical JSON): `{digest}`
- SHA-256 of the cases alone (canonical JSON): `{cases_digest}`

The bundle is published after grading. To check it is the one sealed here:

    shasum -a 256 runs/{tcode}/sealed/bundle.json
"""
    path = os.path.join(ROOT, "runs", tcode, "SEAL.md")
    with open(path, "w") as f:
        f.write(seal)
    print(seal)
    rel = os.path.relpath(path, ROOT)
    subprocess.run(["git", "add", rel], cwd=ROOT, check=True)
    msg = (f"Seal {tcode}: {len(cases)} cases, SHA-256 {digest[:16]}\n\n"
           "The cases and the old transaction's answers stay out of git until grading.\n\n"
           "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
    subprocess.run(["git", "commit", "-q", "-m", msg, "--", rel], cwd=ROOT, check=True)
    if push:
        subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
    return digest


if __name__ == "__main__":
    main(sys.argv[1].upper(), push="--no-push" not in sys.argv)
