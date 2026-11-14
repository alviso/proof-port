# ZCRED: sealed test cases

Sealed 2026-11-14 04:23 UTC, before the port started. The cases were written by an agent from the extract alone, and every
expected result is what the old transaction did when the oracle ran the case.

- Cases: 140 (64 of them end in an error message from the old transaction)
- SHA-256 of `runs/ZCRED/sealed/bundle.json` (cases and answers, canonical JSON): `8422a314f054c9df5123365ee9900b3043eee961d1fb35bcf16d7c6c8f6465a4`
- SHA-256 of the cases alone (canonical JSON): `5e72400f0c35d8be00bc8c5a33f2414fda1841fafdc4b7e8331440aa5aa2f87e`

The bundle is published after grading. To check it is the one sealed here:

    shasum -a 256 runs/ZCRED/sealed/bundle.json
