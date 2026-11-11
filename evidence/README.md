# Verification results

The acceptance runner queries each selected backend through the FastAPI routes. It saves the observed outcomes, exact cents, input SHA-256 values and report revisions. A separate input audit queries the original files independently of the application SQL.

| Run | Result | Measured source fallback |
| --- | --- | ---: |
| [Fixture](fixture.md) · [JSON](fixture.json) | Local rehearsal with independent expected values | 8.24 ms |
| [Full TLC, local](local.md) · [JSON](local.json) | Local DuckDB source and isolated DuckDB candidate | 277.80 ms |
| [Databricks SQL](databricks.md) · [JSON](databricks.json) | Live OAuth connector, versioned managed Delta tables, active read and refresh | 361.76 ms |
| [BigQuery](bigquery.md) · [JSON](bigquery.json) | Live official client, batch-loaded Sandbox tables, active read and refresh | 324.46 ms |

All four runs blocked the two reporting faults and the stale candidate. Each rejected an old approval after the batch changed. Each verified a fresh source read after candidate failure and returned **Report unavailable** for stale and unavailable source tests.

The timer starts when the app detects the simulated candidate failure and ends when it verifies the returned DuckDB report. The provider had served a real report before the simulation in both live runs. The timer measures app-side fallback after detection.

- [Original input audit](input-audit.json) records baseline amounts, exact midnight counts and fee coverage.
- [Civil midnight checks](civil-midnight.json) records counts from the three engines using their provider-specific pickup clock mapping.
- [Verification log](verification.md) records backend tests, browser tests and renamed checkout acceptance.
- Browser captures include [desktop](screenshots/desktop-local-blocked.png), [mobile](screenshots/mobile-local-blocked.png), [Databricks serving](screenshots/databricks-switched.png), [BigQuery serving](screenshots/bigquery-switched.png) and [BigQuery fallback](screenshots/bigquery-fallback.png).
- [Demo guide](../docs/demo.md) lists the locally stored screenshots and recordings.

During an earlier BigQuery API run, an extra refresh took the observed-error fallback path after a successful live switch. The later full acceptance run completed the live refresh and all simulated scenarios. This evidence describes those specific runs.
