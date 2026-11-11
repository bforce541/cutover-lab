# Cutover Lab · DuckDB candidate results

Observed at 2026-11-11T23:04:19+00:00 UTC. Local rehearsal using full inputs.
Connector smoke result `SELECT 1 → 1`.

| Slice | Old trips | Candidate trips | Old recorded fee | Candidate recorded fee | Difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| December | 3,668,337 | 3,668,337 | Unavailable | Unavailable | Unavailable |
| January | 3,475,204 | 3,475,204 | $1,679,955.75 | $1,679,955.75 | $0.00 |
| Jan 6 | 80,126 | 80,126 | $38,831.25 | $38,831.25 | $0.00 |
| Jan 7 | 100,643 | 100,643 | $52,052.25 | $52,052.25 | $0.00 |
| Jan 6 · Midtown Center (161) | 4,342 | 4,342 | $3,077.25 | $2,264.25 | −$813.00 |
| Jan 6 · Midtown East (162) | 3,217 | 3,217 | $2,264.25 | $3,077.25 | $813.00 |

| Scenario | Outcome | Returned backend and batch | Recovery |
| --- | --- | --- | ---: |
| Zone swap | blocked | DuckDB source · current | — |
| Wrong day | blocked | DuckDB source · current | — |
| Stale candidate | blocked | DuckDB source · current | — |
| Stale approval | Old approval rejected (HTTP 409) | — | — |
| Corrected | approved | DuckDB source · current | — |
| Active read | switched | DuckDB candidate · current | — |
| Recovery | fallback | DuckDB source · current | 277.80 ms |
| Fallback stale | unavailable | — | — |
| Fallback unavailable | unavailable | — | — |

Recovery is measured from the detected candidate failure to the first source result that passes the batch and report digest checks. The injected failure bypasses provider transport.

The matching reports compare input fingerprints, key coverage, signed fees and civil pickup clock checks, including the minimum and maximum pickup second for every group.
The JSON companion includes full input hashes and report revisions.
