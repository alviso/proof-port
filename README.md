# Proof Port

Rewriting a custom SAP transaction is easy. Proving the rewrite does the same thing isn't. Proof Port ports one and
lets the old transaction grade the new one, on tests sealed before the port.

Built at EVOLVE, 8090's AI hackathon in Redwood City, 13 to 14 November 2026. This repo was started at the event and
is being built there; its commit history is the record of what was made when.

## What it does

Give it a custom SAP transaction (a module pool: screens, flow logic, ABAP, dictionary) and it hands back a new
implementation on the same database tables, with a proof page saying how closely the two behave.

1. **Extract.** Read the transaction and everything it uses in the customer namespace. SAP's own objects are listed
   by name and never read.
2. **Oracle.** Replay any sequence of screen inputs through the old transaction by batch input and record what the
   screen says and what it leaves in the tables.
3. **Tests.** One agent writes cases from the extract alone; the oracle answers them. The cases are sealed: their
   SHA-256 is committed here before the port starts, and the cases themselves only after grading.
4. **Port.** A second agent, walled off from the cases, builds a RAP business object and an OData V4 service on the
   same tables, with a Fiori Elements app.
5. **Grade.** Every sealed case through the old screen and the new service; compare messages and rows. Then break
   the port on purpose and check the grader goes red.
6. **Proof page.** The score, every difference in words, and what was checked and what wasn't.

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
    python3 factory/app.py ZCRED                  # the new Fiori Elements app on http://127.0.0.1:8100/
    python3 factory/app.py ZMM01 8102
    python3 factory/stage.py                      # the stage page on http://127.0.0.1:8200/
    python3 factory/sofa.py ZCRED [--tests]       # record the run in 8090's Software Factory

`factory/oracle.py` (stage 2) is used by all of them: it replays screen inputs through the old transaction by batch
input and puts the tables back after every case.

## Built before the event

- The legacy transactions are the input and were made before the event: ZCRED (mine) and ZMM01, from
  [trymytoolkit/sap-retail-z-sandbox](https://github.com/trymytoolkit/sap-retail-z-sandbox) (MIT, Romain Hecquet).
  They live on the SAP system, not in this repo.
- The SAP ABAP developer trial runs on a cloud VM under SAP's licence. It is not in this repo, and neither is any SAP
  standard code.
- An earlier private prototype of this approach was built 4 to 9 November 2026. None of its code is in this repo.
  What carried over is what I learned.
- Saybooks, if shown in the demo, is my separate product (AGPL, saybooks.io) and not part of this submission. The
  same goes for the ECC model client, a separate project on the same SAP system.

## Tools and licences

This list grows as the build does.

- Claude Code and Claude Opus 5.5 (Anthropic, under Anthropic's commercial terms): the test author and port agents
- Python standard library (Python Software Foundation License)
- SAP ABAP Development Tools REST interface and batch input, on the SAP ABAP developer trial (SAP's trial licence)
- On the SAP system, called but not copied: `/ui2/cl_json` for JSON, `RPY_DYNPRO_READ` for screen definitions,
  RAP and the OData V4 runtime (SAP's trial licence)
- SAPUI5 and Fiori Elements, served by the SAP system to the local app host (SAP's licence; not in this repo)

## Licence

MIT, see [LICENSE](LICENSE).
