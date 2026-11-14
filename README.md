# Proof Port

Rewriting a custom SAP transaction is easy. Proving the rewrite does the same thing isn't. Proof Port ports one and
lets the old transaction grade the new one, on tests sealed before the port.

Built at EVOLVE, 8090's AI hackathon in Redwood City, 13 to 14 November 2026. This repo was started at the event and
its commit history is the record of what was made when.

## What it showed

Two custom transactions went through the whole factory on the first night. One is mine; the other is a stranger's,
so nobody can say the subject was written to suit the factory.

| | ZCRED | ZMM01 |
|---|---|---|
| What it is | change a customer's credit limit, two screens | create a retail article with variants, five screens, tabs and a table control |
| Whose | mine | [trymytoolkit/sap-retail-z-sandbox](https://github.com/trymytoolkit/sap-retail-z-sandbox), MIT, Romain Hecquet |
| Sealed cases, written by an agent from the extract | 140 | 141 |
| Sealed before the port started | [SEAL.md](runs/ZCRED/SEAL.md), commit 3e0feb1 | [SEAL.md](runs/ZMM01/SEAL.md), commit 511c77f |
| Behave the same, old screen and new app | **139 of 140** | **139 of 141** |
| Differences | c097: the old screen says "Enter a numeric value" for a letter inside a number, the new app says the format | c018: Exit with no article id; c043: a base unit that doesn't exist |
| Breaks to the port caught (newly failing cases) | 3 of 3 (76, 15, 15) | 3 of 3 (44, 33, 6) |
| Port agent saw the cases | no | no (one phrase match, reviewed by hand: a coincidence) |
| Test author agent | 8 min, 3.35 USD | 18 min, 8.54 USD |
| Port agent | 70 min, 45.97 USD | 69 min, 44.55 USD |
| Proof page | [ZCRED proof page](https://alviso.github.io/proof-port/runs/ZCRED/proof.html) | [ZMM01 proof page](https://alviso.github.io/proof-port/runs/ZMM01/proof.html) |

Costs are Claude list prices as Claude Code reported them. Every difference is shown as it is; none was fixed after
grading.

## What it does

Give it a custom SAP transaction (a module pool: screens, flow logic, ABAP, dictionary) and it hands back a new
implementation on the same database tables, with a proof page saying how closely the two behave.

1. **Extract.** Read the transaction and everything it uses in the customer namespace. SAP's own objects are listed
   by name and never read.
2. **Oracle.** Replay any sequence of screen inputs through the old transaction by batch input and record what the
   screen says and every row it leaves in the tables. The tables are put back after each case.
3. **Tests.** One agent writes cases from the extract alone; the oracle answers them. The cases are sealed: the
   SHA-256 of cases and answers is committed and pushed before the port starts, the cases themselves only after
   grading.
4. **Port.** A second agent, walled off from the cases, builds a RAP business object, an OData V4 service and a
   Fiori Elements app on the same tables. It can ask the old transaction about cases of its own, and run the same
   grader on them.
5. **Grade.** Every sealed case through the old screen and through the new service, each from the same data;
   compare the error messages and every row. Then break the port on purpose, three ways, and check the cases catch it.
6. **Proof page.** The score, every difference in words, the seal, the breaks, and what was checked and what wasn't.

## Why the score can be trusted

- **The judge is the old system.** No expected result comes from reading code. Each one is what the old transaction
  did when the oracle ran the case.
- **The tests existed before the code they judge.** Their hash is in a public commit made before the port agent
  started. The bundle published now hashes to the same value: `shasum -a 256 runs/ZCRED/sealed/bundle.json`.
- **The port agent couldn't see them.** The sealed cases were moved out of the project while it worked, and its
  permissions denied reading them anyway. Afterwards [check.py](factory/check.py) searched everything it did and
  wrote for every sealed case id and intent. Both agents' transcripts are in `runs/*/transcripts/`.
- **The port doesn't call the old code.** No CALL TRANSACTION, SUBMIT or batch input in the new objects, and the
  driver only talks to the new OData service.
- **The grader goes red when it should.** Each port was broken three ways (a flipped comparison, a check switched
  off, one letter of a message changed) and each break failed cases that passed before.

## What it doesn't prove

- Batch input proves rules, not display. What a screen shows (names, greyed fields, titles) is only seen through what
  it accepts and what it saves.
- A success message sent just before the transaction ends never reaches batch input, so for saves the rows are the
  evidence.
- Batch input stops at the first error, so retyping after a refusal on the same screen isn't tested.
- F4 value help doesn't run under batch input.
- Timestamps are compared as set or empty, not by value. Warnings and information messages aren't compared.
- ZMM01's tables start empty and a save ends a batch input transaction, so its "change an existing article" branch
  was never reached by a case. The port agent's report says the old program would wipe colour and size there, and
  the new one doesn't.

The agents' reports say what comparing rows can't: [ZCRED](runs/ZCRED/port/REPORT.md), [ZMM01](runs/ZMM01/port/REPORT.md).

## On 8090's Software Factory

ZCRED's run is recorded in a Software Factory project: the extract in the knowledge base, requirements with
acceptance criteria written from the extract, a blueprint of the new objects, the port as a work order with the
grade as its comment, and the 140 sealed cases as 11 test cases with one graded test run (10 passed, the one holding
c097 failed). [sofa.py](factory/sofa.py) does it through their MCP server.

## Running it

Python 3 standard library only. The SAP system is reached through ADT (`SAP_URL`, by default a local tunnel), with
credentials in an env file outside the repo (`SAP_ENV`). The agents are Claude Code, run headless.

    python3 factory/extract.py ZCRED              # stage 1: runs/ZCRED/extract/
    python3 factory/tests.py ZCRED                # stage 3a: an agent writes runs/ZCRED/sealed/cases.json
    python3 factory/seal.py ZCRED                 # stage 3b: oracle answers, SHA-256 committed and pushed
    python3 factory/port.py ZCRED ZPP_CR_         # stage 4: a second agent ports it, cases moved to a vault
    python3 factory/vault.py unlock ZCRED
    python3 factory/check.py ZCRED                # did the port agent see any case? does the port call the old code?
    python3 factory/grade.py ZCRED --sealed --out runs/ZCRED/grade.json    # stage 5
    python3 factory/mutate.py ZCRED               # break the port on purpose, grade each break
    python3 factory/proof.py ZCRED                # stage 6: runs/ZCRED/proof.html
    python3 factory/publish.py ZCRED              # clean the transcripts, scan for secrets, commit and push
    python3 factory/app.py ZCRED                  # the new Fiori Elements app on http://127.0.0.1:8100/
    python3 factory/app.py ZMM01 8102
    python3 factory/stage.py                      # the stage page on http://127.0.0.1:8200/, the talk on /deck
    python3 factory/sofa.py ZCRED [--tests]       # record the run in 8090's Software Factory

`factory/oracle.py` (stage 2) is used by all of them. The briefs the agents get are in `factory/briefs/`.

## Built before the event

- The legacy transactions are the input and were made before the event: ZCRED (mine) and ZMM01, from
  [trymytoolkit/sap-retail-z-sandbox](https://github.com/trymytoolkit/sap-retail-z-sandbox) (MIT, Romain Hecquet).
  They live on the SAP system; their extracts are in `runs/*/extract/`.
- The SAP ABAP developer trial runs on a cloud VM under SAP's licence. It is not in this repo, and neither is any SAP
  standard code.
- An earlier private prototype of this approach was built 4 to 9 November 2026. None of its code is in this repo.
  What carried over is what I learned.
- Saybooks, if shown in the demo, is my separate product (AGPL, saybooks.io) and not part of this submission. The
  same goes for the ECC model client, a separate project on the same SAP system.

## Tools and licences

- Claude Code with Claude Opus 5.5 and Claude Sonnet 5.5 (Anthropic, under Anthropic's commercial terms): the test
  author, port and Software Factory agents
- Python standard library (Python Software Foundation License)
- SAP ABAP Development Tools REST interface and batch input, on the SAP ABAP developer trial (SAP's trial licence)
- On the SAP system, called but not copied: `/ui2/cl_json` for JSON, `RPY_DYNPRO_READ` for screen definitions,
  RAP and the OData V4 runtime (SAP's trial licence)
- SAPUI5 and Fiori Elements, served by the SAP system to the local app host (SAP's licence; not in this repo)
- 8090's Software Factory and its MCP server (8090's terms), for the record of ZCRED's run
- No sponsor tools (HydraDB, Composio, Vercel, ElevenLabs) were used.

## Licence

MIT, see [LICENSE](LICENSE).
