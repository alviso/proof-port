# Brief: port {TCODE} to RAP

The custom SAP transaction {TCODE} (program {PROG}) is being rewritten as a RAP business object with an OData V4
service and a Fiori Elements app, on the same database tables. Afterwards a grader runs cases you have not seen
through the old screen and through your service, each from the same data, and compares the error messages and every
table row. Your job is to make the new one behave the same, and to say honestly where it doesn't.

## What you have

- `runs/{TCODE}/extract/`: everything the factory read. `summary.json` first, then `source/`, `screens.json` (fields
  and flow logic per screen), `status.json` (function codes), `dictionary.json` (tables, fields, domains).
- `python3 factory/rap.py ...`: create, activate and publish RAP objects (run it without arguments for usage). Every
  name must start with `{PREFIX}`. Activation errors come back with the line.
- `python3 factory/oracle.py {TCODE} CASES.json OUT.json`: ask the old transaction what it does for cases you write.
  The case format is at the top of `factory/oracle.py`.
- `python3 factory/grade.py {TCODE} CASES.json`: runs your own cases through the old screen and through your driver
  and new service, and prints every difference. This is the same grader that will judge you.
- `factory/odata.py`: the client your driver gets.

Keep your own cases in `runs/{TCODE}/port/my_cases.json`. Write as many as you need.

## What to deliver, in runs/{TCODE}/port/

1. **RAP objects on SAP**, all named `{PREFIX}...`: CDS view entities over the same tables, a behavior definition, a
   behavior pool with the validations, determinations and actions that reproduce the old checks, with message texts
   identical to the old ones, writes to the same tables the old program writes (including any log), a service
   definition, and an OData V4 UI service binding, activated and published. A metadata extension with UI annotations
   so that a Fiori Elements list report and object page work for a person.
2. **`src/`**: the source of every object you made, one file each (`NAME.ddls`, `.bdef`, `.clas.abap`,
   `.clas.locals_imp.abap`, `.ddlx`, `.srvd`), identical to what is active.
3. **`service.json`**: `{"root": "/sap/opu/odata4/sap/<binding>/srvd/sap/<service definition>/0001/",
   "objects": [["DDLS", "NAME"], ...]}`, every object you made, lowercase names in the root.
4. **`driver.py`** with `def run(client, steps)`. It does with the new service what the case's screen steps do on the
   old screen, the way a person using the new app would. `client` is an `odata.Client`: `get`, `post`, `patch`,
   `delete` with paths relative to the service root; the messages the service sends are collected for you. The
   driver translates screens to calls: which field is which property, which function code means save, back or
   cancel, what typed text means. It holds no business rule: every check lives in the RAP object. The one exception
   is what a UI checks before it calls anything (typed text that is not a number, for example): record that with
   `client.ui("E", text)`. The driver must not read or write tables, run reports or call the old transaction.
5. **`REPORT.md`**: what you built; each old rule and where it lives now; what you could not reproduce; what you
   assumed about screen sequences; and what you noticed that comparing messages and rows cannot show.

## Rules

- Don't read `runs/*/sealed/` or `runs/*/work/`. The permissions block it; don't look for other ways.
- Don't change the old program, the tables' definitions, or any object that doesn't start with `{PREFIX}`. Change
  data only through your service, the oracle or the grader.
- The new service must not call the old transaction or its code: no CALL TRANSACTION, SUBMIT, batch input or
  PERFORM IN PROGRAM.
- The old screen remembers between presses: a field keeps its value after an error, a later screen shows what an
  earlier one loaded, pressing Enter on a screen that saves on a function code does nothing. Decide what a step
  sequence means for the new app, and write it down in REPORT.md.
- Old screens take what fingers type: `!` clears a field, `10.` is not ten, `5-` is minus five in SAP, and this SAP
  user writes numbers as 1.234,56 and dates as DD.MM.YYYY. Ask the oracle how the old screen takes each, and match it.
- If something you started keeps running, stop only that; never `pkill -f`.
- You are done when the grader shows no differences on your own cases (or you can explain each one in REPORT.md),
  and everything is active and published. End with a short summary.
