# Brief: record a Proof Port grade as test results in 8090's Software Factory

The Software Factory project already holds this run's knowledge, requirements ("{TCODE}: what the old transaction
does", with acceptance criteria `AC-{TCODE}-...`), blueprint and work order ("Port {TCODE} to RAP"). The Tests module
is now on. Add the test cases and one test run, through the `software-factory-proof-port` MCP server only. Don't
change the documents or the work order, except to link the test cases to them.

## What you have (read only)

- `runs/{TCODE}/sealed/bundle.json`: the sealed cases (`cases`, each with an id and an intent).
- `runs/{TCODE}/grade.json`: for every case, pass or fail and the differences.
- The requirements document in the project, for the acceptance criteria ids.
- The proof page: https://github.com/alviso/proof-port/blob/main/runs/{TCODE}/proof.html

## What to create

1. **Test cases**: group the sealed cases the way their intents fall, about 8 to 15 groups (such as "customer
   lookup" or "number typing"). One test case per group. Its description lists the case ids in the group, what they
   check, and the acceptance criteria they cover; link it to the requirements document and the work order if the
   tools allow. Every sealed case belongs to exactly one group.
2. **One test run**, "Sealed cases, graded against the old transaction", over these test cases.
3. **Results**: for each test case's execution, passed if every case in the group passed in `grade.json`, failed
   otherwise, with the failing ids and their difference in one line each.

Check first whether earlier test cases already exist in the project, and don't create duplicates. End with a short
list: the groups, their case counts, and their results.
