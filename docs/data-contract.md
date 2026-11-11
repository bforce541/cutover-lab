# Data and report contract

The [TLC data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf) defines `tpep_pickup_datetime`, `PULocationID`, `congestion_surcharge` and `cbd_congestion_fee`. This report uses the last of those fee fields. It measures recorded values in TLC trip records. Some entries are signed and the report keeps them.

## Inputs, time and money

| Engine | Raw pickup column | Civil-date mapping |
| --- | --- | --- |
| DuckDB | Parquet local `TIMESTAMP_MICROS`, `isAdjustedToUTC=false` | Read as a timezone-free timestamp and cast to date. |
| Databricks SQL | Managed Delta `TIMESTAMP_NTZ`, confirmed on both tables | Use a UTC session and cast the pickup clock to `TIMESTAMP_NTZ` before filtering and grouping. |
| BigQuery | Parquet batch load exposed a `TIMESTAMP` | Cast to `DATETIME` using UTC as the carrier for the encoded civil clock, then cast to date. |

The month filter is `start 00:00:00 ≤ pickup < next month 00:00:00`. The source data encodes the civil pickup clock. Applying a New York time-zone conversion to a UTC carrier would change the encoded date for some trips. The tests put records at each side of the month and day boundary. The live clean comparison also checks minimum and maximum pickup seconds and pickup clock sums for every group against DuckDB. The independent input audit counts records at the two demo midnights. All three engines matched the reference of zero pickups at Jan 6 midnight and two at Jan 7 midnight.

The January input has 6,553 negative fee rows, zero null fees and zero fractional-cent fee rows after applying the month filter. Before summing, the engines convert through an exact decimal to signed integer cents. December has no CBD field, so it carries absent availability and a null amount. A present field with null rows carries separate coverage counts. A group with known fees totaling zero displays $0.00. The sample fixture exercises an actual null and an unknown and a missing pickup zone. Zone labels are resolved after grouping so these keys remain visible.

## Two batches and one approval

- **December only** reads the December file/table. **Dec + Jan** reads both months. Start dates, end dates, field availability and verified file SHA-256 values are attached to the query. File-derived table names identify the loads. Databricks additionally pins the Delta version.
- Each provider groups original rows by month, day, and day plus pickup-zone ID. The comparison checks key uniqueness and coverage, counts, fee availability, nulls, negative fee count, exact cents, and civil clock invariants. The projection check combines pickup seconds, zone and signed fee for each row. These comparisons verify the fields used by the report. They cannot prove byte-for-byte equivalence of cloud table storage or equality of unused columns.
- A successful check records both report digests and their selection, batch and revision. A fresh read at switch time must match those digests. The API rejects an old approval after the selection changes, and serializes actions to prevent overlapping transitions. The report revision is derived from the executed SQL templates and their dialect projections.
- The approved query is separate from the two injected SQL variants. The zone swap changes only the two reported Jan 6 zone amounts. The wrong-day variant takes the Jan 6 fee total off its day and zone breakdown, assigns it to Jan 7, and uses zone 161 as the receiving bucket for Jan 7's detail. Trips and the January fee total stay fixed.
- Once the candidate has served successfully, an injected or observed error can route to a fresh source query. The source batch and entire report digest must match the verified source. Recovery time runs from detection of the failed candidate attempt until the first verified fallback result, using a monotonic clock. An injected error is raised in the app before a network attempt. The number therefore measures recovery after detection.

The benchmark evidence covers this historical public batch on the recorded machine. A production migration would separately test freshness SLAs, late-arriving data, authentication and access policies, incidents with genuine network timeouts, retention, distributed concurrency, and ongoing correctness after new batches arrive.
