# Cutover Lab · DuckDB candidate results

Observed at 2026-11-11T23:04:20+00:00 UTC. Local rehearsal using fixture inputs.
Connector smoke result `SELECT 1 → 1`.

| Slice | Old trips | Candidate trips | Old recorded fee | Candidate recorded fee | Difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| December | 2 | 2 | Unavailable | Unavailable | Unavailable |
| January | 10 | 10 | $9.50 | $9.50 | $0.00 |
| Jan 6 | 6 | 6 | $4.25 | $4.25 | $0.00 |
| Jan 7 | 2 | 2 | $3.75 | $3.75 | $0.00 |
| Jan 6 · Midtown Center (161) | 3 | 3 | $3.00 | $1.25 | −$1.75 |
| Jan 6 · Midtown East (162) | 1 | 1 | $1.25 | $3.00 | $1.75 |

| Scenario | Outcome | Returned backend and batch | Recovery |
| --- | --- | --- | ---: |
| Zone swap | blocked | DuckDB source · current | — |
| Wrong day | blocked | DuckDB source · current | — |
| Stale candidate | blocked | DuckDB source · current | — |
| Stale approval | Old approval rejected (HTTP 409) | — | — |
| Corrected | approved | DuckDB source · current | — |
| Active read | switched | DuckDB candidate · current | — |
| Recovery | fallback | DuckDB source · current | 8.24 ms |
| Fallback stale | unavailable | — | — |
| Fallback unavailable | unavailable | — | — |

Recovery is measured from the detected candidate failure to the first source result that passes the batch and report digest checks. The injected failure bypasses provider transport.

The matching reports compare input fingerprints, key coverage, signed fees and civil pickup clock checks, including the minimum and maximum pickup second for every group.
The JSON companion includes full input hashes and report revisions.
