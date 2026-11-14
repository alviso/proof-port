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

- Claude Code and Claude models (Anthropic, under Anthropic's commercial terms)
- Python standard library (Python Software Foundation License)
- SAP ABAP Development Tools REST interface and batch input, on the SAP ABAP developer trial (SAP's trial licence)

## Licence

MIT, see [LICENSE](LICENSE).
