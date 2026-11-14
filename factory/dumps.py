"""Print the latest short dumps on the SAP system: time, program and short text."""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sap  # noqa: E402


def latest(n=3):
    s = sap.Sap()
    _, _, text = s.request("GET", f"/sap/bc/adt/runtime/dumps?$top={n}", accept="application/atom+xml;type=feed")
    out = []
    for entry in re.findall(r"<atom:entry.*?</atom:entry>", text, re.S)[:n]:
        title = re.search(r"<atom:title[^>]*>(.*?)</atom:title>", entry, re.S)
        when = re.search(r"<atom:updated>(.*?)</atom:updated>", entry)
        body = html.unescape(html.unescape(entry))
        prog = re.search(r'Program&nbsp;</b></td><td nowrap>\s*(\S+)', body)
        line = re.search(r"termination point is in line (\d+)", body)
        out.append(f"{when.group(1) if when else '?'} {prog.group(1) if prog else '?'} "
                   f"line {line.group(1) if line else '?'}: {html.unescape(title.group(1)) if title else '?'}")
    return out


if __name__ == "__main__":
    print("\n".join(latest(int(sys.argv[1]) if len(sys.argv) > 1 else 3)))
