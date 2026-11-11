# When should finance switch the daily report?

The new report needs to give the same numbers that finance uses to make decisions. A matching daily total is a good start. The finance team also needs the right fees in the right pickup zones, and the report needs to cover the latest agreed batch.

We ran the old and candidate reports in parallel on NYC yellow taxi trip records. On January 6, both showed **80,126 trips** and **$38,831.25 in recorded CBD fees**. The candidate put **$813.00 too little** in Midtown Center and **$813.00 too much** in Midtown East. Finance would have seen the wrong zone breakdown even though the headline figures agreed. The rehearsal blocked the switch and the old report kept serving.

**Hold** if a month, day or zone differs, fee data is missing, or the candidate is behind the source batch. **Switch** after fresh checks pass for the corrected report, then verify that the selected warehouse is serving it. The rehearsal demonstrated this with live Databricks SQL and BigQuery reads.

**Switch back** if the candidate cannot serve the report and the old system can return the same verified current batch. The rehearsal deliberately failed the candidate after it had served successfully. A fresh DuckDB query returned the verified batch. When the source was stale or unavailable, the screen displayed **Report unavailable**.

Before a production move, agree how late data can arrive, who can approve and roll back, how to reconcile repeated daily loads, and how long finance can operate without a report. Rehearse a real connectivity incident, measure time to detect it, and verify the rollback in the production environment with business owners. The taxi records and simulated faults demonstrate the decision process. They do not represent company revenue or actual NYC collections.
