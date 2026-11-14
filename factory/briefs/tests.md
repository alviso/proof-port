# Brief: write test cases for {TCODE}

You are the test author. The custom SAP transaction {TCODE} (program {PROG}) is going to be rewritten as a new app
on the same database tables. The old transaction stays the judge: whatever it does for a case is the expected
result. So you don't predict outcomes. You choose inputs that will show whether the new app behaves the same.

## What you have

- `runs/{TCODE}/extract/`: what the factory read from the system. `summary.json` first, then `source/`,
  `screens.json` (fields and flow logic per screen), `status.json` (function codes and titles), `messages.json`,
  `dictionary.json` (tables, fields, data elements, domains).
- The oracle: `python3 factory/oracle.py {TCODE} <cases.json> <out.json>` runs cases through
  the old transaction by batch input and writes what it said and every table row afterwards. It restores the tables
  after each case, so cases never affect each other. Use it to check your cases are well formed.

## What to write

`runs/{TCODE}/sealed/cases.json`: a JSON list of cases. Each case:

```json
{"id": "c001", "intent": "one sentence: what this case checks",
 "steps": [{"screen": "0100", "fields": {"GV_KUNNR": "C100"}, "ok": "/00"},
           {"screen": "0200", "fields": {"GV_NEW_LIMIT": "7000"}, "ok": "SAVE"}]}
```

A step is one screen: the fields typed into it and the function code pressed (`/00` is Enter; the others are in
`status.json` and the flow logic). Ids run c001, c002, ... without gaps.

Cover, for a transaction this size, 80 to 150 cases:

- Every rule and every message in the source, and each boundary from both sides (just under, at, just over).
- Every function code on every screen, including Back, Exit and Cancel, and what happens to unsaved input.
- Sequences across screens where memory between presses matters: go forward, come back, choose another record,
  save twice, change one field and not another.
- What a user's fingers produce: leading and trailing spaces, lowercase, an empty field, `!` (clears a field on an
  old screen), `10.`, `1.000`, `1.000,50`, `-5`, `5-` (SAP's trailing minus), zero, very long values, letters in a
  number field. The SAP user types numbers as 1.234,56 and dates as DD.MM.YYYY.
- Every record in the seed data that behaves differently (blocked, special currency, priority and so on).

Batch input ends a case with "No batch input data for screen ..." when the steps run out on a screen. That is fine
when you meant to stop there; it is a sign of a malformed case when you didn't.

## Rules

- Write only inside `runs/{TCODE}/sealed/`. Change nothing on the SAP system and nothing else in the repo.
- Don't try to guess or record expected results. The factory asks the oracle after you finish.
- Finish with a short report (in your last message): how many cases, what they cover, and what you could not test
  this way (for example F4 help or what a screen displays).
