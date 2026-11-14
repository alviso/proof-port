# ZMM01: sealed test cases

Sealed 2026-11-14 04:46 UTC, before the port started. The cases were written by an agent from the extract alone, and every
expected result is what the old transaction did when the oracle ran the case.

- Cases: 141 (39 of them end in an error message from the old transaction)
- SHA-256 of `runs/ZMM01/sealed/bundle.json` (cases and answers, canonical JSON): `9e3220f78683f4e61a1c77611ac2e57df019fdcc84e9dec69b6ab55c5c9a49f5`
- SHA-256 of the cases alone (canonical JSON): `2ff84c583ec3217967e431eab256132421ad385b8bd5722891ea926e8b33b212`

The bundle is published after grading. To check it is the one sealed here:

    shasum -a 256 runs/ZMM01/sealed/bundle.json
