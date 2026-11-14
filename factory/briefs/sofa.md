# Brief: record a Proof Port run in 8090's Software Factory

Proof Port has finished a run for the SAP transaction {TCODE}: extract, sealed cases, port to RAP, grade. Record it
in the Software Factory project through the `software-factory-proof-port` MCP server, so the project shows the same
story in its own terms: knowledge, requirements, a work order, test cases and their results. Use only that server.

## What you have (read only)

- `runs/{TCODE}/extract/`: what the factory read from the old system (`summary.json`, `source/`, `screens.json`).
- `runs/{TCODE}/sealed/bundle.json`: the sealed cases (`cases`, each with an id and an intent) and the old
  transaction's answers. Published after grading; fine to use now.
- `runs/{TCODE}/grade.json`: for every case, pass or fail and the differences. `runs/{TCODE}/mutants.json`,
  `runs/{TCODE}/check.json`, `runs/{TCODE}/SEAL.md`, `runs/{TCODE}/port/REPORT.md`, `runs/{TCODE}/port/service.json`.
- The public repo is https://github.com/alviso/proof-port and the proof page is
  https://github.com/alviso/proof-port/blob/main/runs/{TCODE}/proof.html

## What to create

1. **Knowledge Base**: upload `runs/{TCODE}/extract/summary.json` and the program source from
   `runs/{TCODE}/extract/source/` (request an upload URL, PUT the file with curl, then save it).
2. **Requirements**: one feature document, "{TCODE}: what the old transaction does", written from the extract only.
   Numbered requirements `REQ-{TCODE}-001`... with acceptance criteria `AC-{TCODE}-001.1`... in "shall" form, one per
   rule the old code enforces (checks, messages with their exact text, what gets written). Invent nothing: every
   criterion must point at the source (name the module or form). Accept your own document so it is not left as a
   pending suggestion.
3. **Blueprint**: one document, "{TCODE} on RAP", from `port/REPORT.md` and `port/service.json`: the objects, which
   old rule lives where. Link it to the requirements document.
4. **Work order**: "Port {TCODE} to RAP", linked to both documents, in the status that means done. A comment with the
   result: cases passed of sealed, each difference in one line, mutants caught, whether the port agent saw the cases,
   the seal hash and commit, and the proof page link.
5. **Test cases**: group the sealed cases the way their intents fall (about 8 to 15 groups, such as "customer
   lookup" or "number typing"), one test case per group, naming its case ids and the acceptance criteria it covers.
   Then one test run, and record each group's result: passed if every case in it passed, failed otherwise with the
   failing ids.

Work with what the tools allow; if one of these can't be done, say so and go on. End with a short list of what you
created.
