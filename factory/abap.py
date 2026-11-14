"""Run a generated ABAP report and read back what it writes.

The report writes records as JSON. A list line is limited in width, so each record goes out in chunks of 200
characters, every chunk between '>' and '|' so that trailing spaces survive, and '<<END>>' closes the record.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sap  # noqa: E402

OUT_FORM = r"""
FORM out USING iv_kind TYPE csequence iv_json TYPE string.
  DATA lv_all TYPE string.
  DATA lv_line TYPE string.
  DATA lv_off TYPE i.
  DATA lv_len TYPE i.
  DATA lv_n TYPE i.
  lv_all = iv_kind && ` ` && iv_json.
  lv_len = strlen( lv_all ).
  WHILE lv_off < lv_len.
    lv_n = nmin( val1 = 200 val2 = lv_len - lv_off ).
    lv_line = '>' && substring( val = lv_all off = lv_off len = lv_n ) && '|'.
    WRITE / lv_line.
    lv_off = lv_off + lv_n.
  ENDWHILE.
  WRITE / '<<END>>'.
ENDFORM.
"""


def build(name, body, types=""):
    return f"REPORT {name.lower()} LINE-SIZE 255 NO STANDARD PAGE HEADING.\n{types}\nSTART-OF-SELECTION.\n{body}\n{OUT_FORM}"


def parse(text):
    records, buf = [], []
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith(">") and line.endswith("|"):
            buf.append(line[1:-1])
        elif line.strip() == "<<END>>":
            record = "".join(buf)
            kind, _, payload = record.partition(" ")
            records.append((kind, payload))
            buf = []
    return records


def run(s, name, body, types=""):
    return parse(s.run_abap(build(name, body, types), name=name))
