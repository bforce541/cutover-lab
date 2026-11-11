# Owner walkthrough

## Run the demo

Build the frontend and start FastAPI using the [README commands](../README.md). Use full-data mode for the portfolio figures and **DuckDB candidate** for a credential-free presentation. To demonstrate a real warehouse, switch the target selector to Databricks SQL or BigQuery and verify the masthead shows **Live warehouse** after checks run.

1. Start with **Midtown fee swap** and run checks. Point to the two matching totals, then the two highlighted zones. The old system is serving.
2. Select **Corrected report** and run checks again. The decision reads **Ready for approval**. Click **Switch to cloud**, then show the serving backend and active report in Activity.
3. Click **Simulate failure**. Show the DuckDB source, the Dec + Jan batch and the measured duration in the latest activity. To demonstrate an unavailable result, reset and switch cleanly, then select **Stale source** under **Failure test** before simulating the failure.

## Trace Midtown Center’s $3,077.25

- In January’s original Parquet, each trip carries a pickup timestamp, `PULocationID` and recorded CBD fee. Zone 161 is Midtown Center in the lookup.
- [The pickup projection](../migration_rehearsal/query.py) filters the January file to its month, casts the pickup clock to a civil day, and converts signed fees to integer cents before summing. It attaches the SHA-256 of the original file and includes coverage fields.
- [The common report SQL](../migration_rehearsal/sql/report.sql) uses grouping sets. The key `('zone', '2025-01-01', '2025-01-06', 161)` has 4,342 trips and 307,725 cents on the source. The separate [swap SQL](../migration_rehearsal/sql/zone_swap.sql) reports 226,425 cents at that key on the candidate.
- [The comparison](../migration_rehearsal/comparison.py) aligns the two keyed rows and computes candidate minus source as `226425 − 307725 = −81300` cents. It compares counts, fees and availability before formatting. The React table displays `−$813.00` and zero trip difference. The opposite Midtown East delta balances this amount at the day level.

## Explain freshness and routing

The earlier batch is December only. The current batch includes December and January. The provider receives that batch and queries the corresponding set of original files or versioned tables. Row aggregates carry file fingerprints, covered periods, field availability, and pickup and fee checks. The stale scenario actually queries December only, so the app can show which month is missing.

The selected provider changes the warehouse relation, connection and SQL dialect. The business grouping and comparison stay the same. A passing comparison saves both report digests and the selection, including the SQL revision. Selecting a different target, scenario or batch invalidates the approval. The API also compares the approved digests to fresh reads at switch time. The app then renders the result returned by the newly active adapter.

The failure button requires a previous successful switch. It raises a labeled failure in the candidate path, starts a monotonic clock at detection, then queries DuckDB fresh. The source must match the verified batch and digest. A stale or unavailable source yields a report unavailable state. The measured interval omits real provider failure detection and the browser response time.

## Exercises

1. Recreate the Jan 6/Jan 7 failure. Check Month first, then Day. Explain why the January total agrees and calculate both daily deltas from the source data.
2. Run clean checks, switch the batch to December only, and try the old approval using the API. Follow `test_changed_selection_invalidates_approval` to see the HTTP 409 assertion.
3. Use the fixture and inspect zone 900 plus the missing zone on January 6. Explain the difference between a null amount, an absent fee field and zero dollars.
4. Run `scripts.audit_inputs` on the full input and use `scripts.boundaries --live` to compare the midnight counts. Explain why applying a New York timezone shift to the BigQuery carrier would change some business days.

## Interview questions

**Why were totals insufficient?** The allocation error cancels out across the zones. The operational decision needs keys at the grain finance uses. I checked month, day and pickup-zone rows, plus key coverage and signed fee amounts.

**How did you avoid money drift?** Each adapter converted the raw fee through a decimal to signed integer cents before aggregation. The comparison used exact integers and separate availability and null counts.

**What makes the approval safe to use?** It references the selected provider, batch and revision and the complete checked reports. The server rejects stale versions, serializes actions and re-reads both reports at approval time.

**What was actually cloud-backed?** Databricks SQL computed on managed Delta tables and BigQuery computed on its own batch-loaded tables. In each run the active report came from the corresponding live adapter before failure was injected. DuckDB served the validated fallback.

**What would you validate in production?** Real provider failure detection, end-to-end time objectives, late-arriving data, who can approve, durable state across instances, and fresh comparisons across repeated batches.

## Candidate résumé bullets

- Built a FastAPI and React migration rehearsal that reconciled 7.14M NYC taxi records across DuckDB, Databricks SQL and BigQuery, catching offsetting $813 zone errors despite matching daily totals.
- Enforced batch- and revision-bound cutover approvals and verified live warehouse reads, current-batch DuckDB fallback, and fail-closed handling when fallback data was stale or unavailable.
