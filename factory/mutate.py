"""Grade the grader: break the port on purpose and check the sealed cases catch it.

Makes small edits to the port's behavior implementation (flip a comparison, switch off a check, change a message
text), activates each, grades the sealed cases, and puts the original back. A mutant nobody catches is a gap in the
cases, and the proof page says so.

    python3 factory/mutate.py ZCRED [max_mutants]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import grade  # noqa: E402
import rap  # noqa: E402
import sap  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def behavior_classes(tcode):
    with open(os.path.join(ROOT, "runs", tcode, "port", "service.json")) as f:
        service = json.load(f)
    return [n for k, n in service["objects"] if k.upper() == "CLAS"]


def mutants(source):
    """Yield (description, mutated source). Each changes one place."""
    lines = source.split("\n")
    flips = {"<=": ">", ">=": "<", "<": ">=", ">": "<="}
    done = 0
    for i, line in enumerate(lines):
        code = line.split('"')[0]
        if re.match(r"\s*(ELSE)?IF\b", code, re.I):
            m = re.search(r"(?<![-=<>])(<=|>=|<|>)(?![>=])", code)
            if m:
                new = line[:m.start()] + flips[m.group(1)] + line[m.end():]
                yield (f"line {i + 1}: '{m.group(1)}' became '{flips[m.group(1)]}'",
                       "\n".join(lines[:i] + [new] + lines[i + 1:]))
                done += 1
                break
    for i, line in enumerate(lines):
        code = line.split('"')[0]
        m = re.match(r"(\s*)IF\s+(.+)\.\s*$", code, re.I)
        if m and any(re.search(r"reported|new_message|MESSAGE", x, re.I) for x in lines[i + 1:i + 8]):
            new = f"{m.group(1)}IF 1 = 0. \" mutant: was IF {m.group(2)}"
            yield (f"line {i + 1}: the check 'IF {m.group(2).strip()[:60]}' switched off",
                   "\n".join(lines[:i] + [new] + lines[i + 1:]))
            break
    for i, line in enumerate(lines):
        m = re.search(r"text\s*=\s*'([^']{6,})'", line, re.I)
        if m:
            old = m.group(1)
            changed = old[:-1] + ("x" if old[-1] != "x" else "y")
            yield (f"line {i + 1}: message text '{old}' became '{changed}'",
                   "\n".join(lines[:i] + [line.replace(f"'{old}'", f"'{changed}'", 1)] + lines[i + 1:]))
            break


def main(tcode, limit=3):
    s = sap.Sap()
    bundle_path = os.path.join(ROOT, "runs", tcode, "sealed", "bundle.json")
    with open(bundle_path) as f:
        bundle = json.load(f)
    results = []
    for cls in behavior_classes(tcode):
        original = rap.get(s, "CLAS", cls, "implementations")
        if not re.search(r"\bIF\b", original):
            continue
        for desc, mutated in mutants(original):
            if len(results) >= limit:
                break
            entry = {"object": cls, "change": desc}
            try:
                rap.put(s, "CLAS", cls, mutated, part="implementations")
                errs = [m for m in rap.activate(s, [("CLAS", cls)]) if m.startswith(("E", "A"))]
                if errs:
                    entry["result"] = "did not activate; not counted"
                    entry["errors"] = errs[:3]
                else:
                    report = grade.grade(tcode, bundle["cases"], "ZPP_RESTORE", "ZPP_ORACLE_G", s)
                    entry["failing_cases"] = report["failed"]
                    entry["caught"] = report["failed"] > 0
                    entry["examples"] = [r["id"] for r in report["results"] if not r["pass"]][:8]
            finally:
                rap.put(s, "CLAS", cls, original, part="implementations")
                back = [m for m in rap.activate(s, [("CLAS", cls)]) if m.startswith(("E", "A"))]
                entry["restored"] = not back
            print(json.dumps(entry))
            results.append(entry)
    out = os.path.join(ROOT, "runs", tcode, "mutants.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=1)
    return results


if __name__ == "__main__":
    main(sys.argv[1].upper(), int(sys.argv[2]) if len(sys.argv) > 2 else 3)
