"""Check exact civil-midnight assignments on each loaded engine."""
import argparse
import json
from datetime import datetime, timezone

from migration_rehearsal.config import configure
from migration_rehearsal.inputs import Inputs, ROOT
from migration_rehearsal.providers import BigQuery, Databricks, DuckDB
from migration_rehearsal.query import pickup_projection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Query both configured live adapters.")
    args = parser.parse_args()
    configure()
    audit = json.loads((ROOT / "evidence/input-audit.json").read_text())
    expected = audit["exact_midnight_pickups"]
    inputs = Inputs("full")
    providers = [DuckDB(inputs, "DuckDB source")]
    if args.live:
        providers += [Databricks(inputs), BigQuery(inputs)]
    results = {}
    january = inputs.files[1]
    for provider in providers:
        projection = pickup_projection(january, provider.relation(january), provider.dialect)
        dates = ("2025-01-06", "2025-01-07")
        epochs = [int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) for day in dates]
        query = f"""
            WITH pickups AS ({projection})
            SELECT pickup_day, clock_seconds, COUNT(*) AS trips
            FROM pickups WHERE clock_seconds IN ({epochs[0]}, {epochs[1]})
            GROUP BY pickup_day, clock_seconds
        """
        rows = provider.execute(query)
        result = {day: 0 for day in dates}
        for row in rows:
            day = str(row["pickup_day"])
            assert row["clock_seconds"] == epochs[dates.index(day)]
            result[day] = row["trips"]
        assert result == expected, (provider.name, result, expected)
        results[provider.name] = result
    print(json.dumps({
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_file_sha256": january.sha256,
        "civil_midnight_trips_by_engine": results,
    }, indent=2))


if __name__ == "__main__":
    main()
