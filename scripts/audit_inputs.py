"""Independent baseline query against the downloaded TLC Parquet files."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb

from migration_rehearsal.inputs import BRAND, Inputs
from scripts.verify import FULL


def main() -> None:
    inputs = Inputs("full")
    december, january = (str(item.path) for item in inputs.files)
    with duckdb.connect(":memory:") as db:
        old = db.execute(
            """SELECT COUNT(*)
               FROM read_parquet(?)
               WHERE tpep_pickup_datetime >= TIMESTAMP '2024-12-01'
                 AND tpep_pickup_datetime <  TIMESTAMP '2025-01-01'""",
            [december],
        ).fetchone()[0]
        fees = db.execute(
            """WITH jan AS (
                   SELECT tpep_pickup_datetime AS pickup, PULocationID AS zone,
                          cbd_congestion_fee AS fee
                   FROM read_parquet(?)
                   WHERE tpep_pickup_datetime >= TIMESTAMP '2025-01-01'
                     AND tpep_pickup_datetime <  TIMESTAMP '2025-02-01'
               ), slices AS (
                   SELECT 'january' AS slice, fee FROM jan
                   UNION ALL SELECT 'jan6', fee FROM jan
                       WHERE pickup >= TIMESTAMP '2025-01-06' AND pickup < TIMESTAMP '2025-01-07'
                   UNION ALL SELECT 'jan7', fee FROM jan
                       WHERE pickup >= TIMESTAMP '2025-01-07' AND pickup < TIMESTAMP '2025-01-08'
                   UNION ALL SELECT 'zone161', fee FROM jan WHERE zone = 161
                       AND pickup >= TIMESTAMP '2025-01-06' AND pickup < TIMESTAMP '2025-01-07'
                   UNION ALL SELECT 'zone162', fee FROM jan WHERE zone = 162
                       AND pickup >= TIMESTAMP '2025-01-06' AND pickup < TIMESTAMP '2025-01-07'
               )
               SELECT slice, COUNT(*), CAST(SUM(CAST(fee AS DECIMAL(20,2))) * 100 AS BIGINT),
                      COUNT(*) FILTER (WHERE fee < 0), COUNT(*) FILTER (WHERE fee IS NULL),
                      COUNT(*) FILTER (WHERE fee != ROUND(fee, 2))
               FROM slices GROUP BY slice""",
            [january],
        ).fetchall()
        columns = {
            key: [column[0].lower() for column in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [path]).fetchall()]
            for key, path in (("december", december), ("january", january))
        }
        midnight = db.execute(
            """SELECT COUNT(*) FILTER (WHERE tpep_pickup_datetime = TIMESTAMP '2025-01-06 00:00:00'),
                      COUNT(*) FILTER (WHERE tpep_pickup_datetime = TIMESTAMP '2025-01-07 00:00:00')
               FROM read_parquet(?)""",
            [january],
        ).fetchone()
    baseline = {"december": (old, None), **{row[0]: row[1:3] for row in fees}}
    coverage = {row[0]: dict(zip(("negative", "null", "fractional_cent"), row[3:], strict=True)) for row in fees}
    assert baseline == FULL
    assert coverage["january"] == {"negative": 6553, "null": 0, "fractional_cent": 0}
    assert "cbd_congestion_fee" not in columns["december"]
    assert {"cbd_congestion_fee", "congestion_surcharge"} <= set(columns["january"])
    print(json.dumps({
        "title": f"{BRAND['name']} · Independent TLC input audit",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "batch": inputs.identity("current"),
        "baseline_trips_and_cents": baseline,
        "fee_row_coverage": coverage,
        "exact_midnight_pickups": {"2025-01-06": midnight[0], "2025-01-07": midnight[1]},
    }, indent=2))


if __name__ == "__main__":
    main()
