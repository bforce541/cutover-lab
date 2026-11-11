from __future__ import annotations

import hashlib

from .inputs import ROOT, TripFile

SQL_DIR = ROOT / "migration_rehearsal/sql"
TEMPLATES = {file.stem: file.read_text() for file in sorted(SQL_DIR.glob("*.sql"))}
PROJECTION_CODE = (ROOT / "migration_rehearsal/query.py").read_text()
FAULTS = {"swap": "zone_swap", "wrong_day": "wrong_day"}


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def pickup_projection(item: TripFile, relation: str, dialect: str) -> str:
    if dialect == "bigquery":
        clock = "CAST(tpep_pickup_datetime AS DATETIME)"
        seconds = f"DATETIME_DIFF({clock}, DATETIME '1970-01-01 00:00:00', SECOND)"
        decimal_type, integer = "NUMERIC", "INT64"
        timestamp_type = "DATETIME"
    elif dialect == "databricks":
        clock = "CAST(tpep_pickup_datetime AS TIMESTAMP_NTZ)"
        seconds = f"TIMESTAMPDIFF(SECOND, CAST('1970-01-01 00:00:00' AS TIMESTAMP_NTZ), {clock})"
        decimal_type, integer = "DECIMAL(20, 2)", "BIGINT"
        timestamp_type = "TIMESTAMP_NTZ"
    else:
        clock = "CAST(tpep_pickup_datetime AS TIMESTAMP)"
        seconds = f"date_diff('second', TIMESTAMP '1970-01-01 00:00:00', {clock})"
        decimal_type, integer = "DECIMAL(20, 2)", "BIGINT"
        timestamp_type = "TIMESTAMP"

    cents = f"CAST(CAST(cbd_congestion_fee AS {decimal_type}) * 100 AS {integer})"
    if dialect == "bigquery":
        cents = "CAST(ROUND(CAST(cbd_congestion_fee AS NUMERIC), 2) * 100 AS INT64)"
    if not item.fee_available:
        cents = f"CAST(NULL AS {integer})"

    return f"""
        SELECT DATE '{item.start}' AS month_start,
               CAST({clock} AS DATE) AS pickup_day,
               CAST(PULocationID AS {integer}) AS zone,
               {cents} AS cents,
               {seconds} AS clock_seconds,
               '{item.sha256}' AS input_id,
               {int(item.fee_available)} AS has_fee
        FROM {relation}
        WHERE {clock} >= CAST('{item.start} 00:00:00' AS {timestamp_type})
          AND {clock} < CAST('{item.end} 00:00:00' AS {timestamp_type})
    """


def report_sql(items: tuple[TripFile, ...], relations: list[str], dialect: str, scenario: str) -> str:
    inputs = " UNION ALL ".join(
        pickup_projection(item, relation, dialect)
        for item, relation in zip(items, relations, strict=True)
    )
    fault = FAULTS.get(scenario)
    result = TEMPLATES[fault] if fault else "SELECT g.*, g.fee_cents AS reported_cents FROM report_groups g"
    return TEMPLATES["report"].format(inputs=inputs, result=result)


def report_revision(scenario: str) -> str:
    text = TEMPLATES["report"] + TEMPLATES.get(FAULTS.get(scenario, ""), "")
    text += PROJECTION_CODE
    return hashlib.sha256(text.encode()).hexdigest()
