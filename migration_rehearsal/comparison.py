from __future__ import annotations

import hashlib
import json
from collections import Counter

from .providers import Report

GRAINS = ("month", "day", "zone")
SLICES = ("2025-01-06", "2025-01-07")
CHECK_FIELDS = {
    "trips": "Trip count",
    "has_fee": "Fee field availability",
    "present_fees": "Non-null fee coverage",
    "null_fees": "Null fee coverage",
    "negative_fees": "Negative fee coverage",
    "input_id": "Input fingerprint",
    "pickup_clock_sum": "Civil pickup times",
    "projected_sum": "Input projection",
    "first_pickup": "First pickup",
    "last_pickup": "Last pickup",
    "fee_cents": "Recorded fee amount",
}


def key(row: dict) -> tuple:
    return tuple(row[field] for field in ("grain", "month_start", "pickup_day", "zone"))


def order(row_key: tuple) -> tuple:
    grain, month, day, zone = row_key
    return GRAINS.index(grain), month, day or "", -1 if zone is None else zone


def rows_by_key(report: Report) -> dict[tuple, dict]:
    return {key(row): row for row in report.rows}


def shape_errors(report: Report, expected: dict) -> list[str]:
    errors = []
    if report.batch != expected:
        errors.append(f"{report.backend} returned batch {report.batch['name']}, expected {expected['name']}.")
    months = {item["start"]: item for item in expected["inputs"]}
    if {row["month_start"] for row in report.rows if row["grain"] == "month"} != set(months):
        errors.append(f"{report.backend} returned incomplete month coverage.")
    if len(rows_by_key(report)) != len(report.rows):
        errors.append(f"{report.backend} returned duplicate report keys.")
    for row in report.rows:
        item = months.get(row["month_start"])
        if not item or row["input_id"] != item["sha256"]:
            errors.append(f"{report.backend} returned an unexpected input fingerprint.")
            break
        if row["has_fee"] != int(item["fee_available"]):
            errors.append(f"{report.backend} returned incorrect fee field availability.")
            break
        expected_coverage = row["trips"] if row["has_fee"] else 0
        if (row["present_fees"] + row["null_fees"] != expected_coverage
                or (row["fee_cents"] is None) != (row["present_fees"] == 0)
                or not 0 <= row["negative_fees"] <= row["present_fees"]):
            errors.append(f"{report.backend} returned inconsistent fee coverage.")
            break
    return errors


def report_digest(report: Report) -> str:
    rows = sorted(report.rows, key=lambda row: order(key(row)))
    content = json.dumps([report.backend, report.binding, report.batch, report.revision, rows], sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def zone_name(zones: dict, zone: int | None) -> str:
    if zone is None:
        return "Missing pickup zone"
    return zones.get(zone, f"Unknown zone {zone}")


def report_view(report: Report | None) -> dict | None:
    if report is None:
        return None
    rows = rows_by_key(report)
    return {
        "backend": report.backend,
        "live": report.live,
        "batch": report.batch,
        "revision": report.revision,
        "focus": {
            day: summarize(rows.get(("day", day[:7] + "-01", day, None))) for day in SLICES
        },
    }


def summarize(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {field: row[field] for field in
            ("trips", "fee_cents", "present_fees", "null_fees", "negative_fees", "has_fee")}


def compare(source: Report, candidate: Report, expected: dict, zones: dict) -> dict:
    blockers = shape_errors(source, expected) + shape_errors(candidate, expected)
    old_rows, new_rows = rows_by_key(source), rows_by_key(candidate)
    checks = Counter()
    failures = Counter()
    mismatches = []
    display = []
    for row_key in sorted(old_rows.keys() | new_rows.keys(), key=order):
        grain, month, day, zone = row_key
        old, new = old_rows.get(row_key), new_rows.get(row_key)
        checks[grain] += 1
        if old is None or new is None:
            issues = ["Missing candidate key" if new is None else "Extra candidate key"]
        else:
            issues = [label for field, label in CHECK_FIELDS.items() if old[field] != new[field]]
        if issues:
            failures[grain] += 1
        if grain == "month" or day in SLICES or issues:
            old_fee = old["fee_cents"] if old else None
            new_fee = new["fee_cents"] if new else None
            row = {
                "grain": grain, "month": month, "day": day, "zone": zone,
                "zone_name": zone_name(zones, zone) if grain == "zone" else None,
                "old": summarize(old), "candidate": summarize(new),
                "fee_difference": new_fee - old_fee if old_fee is not None and new_fee is not None else None,
                "trip_difference": new["trips"] - old["trips"] if old and new else None,
                "issues": issues,
            }
            if grain == "month" or day in SLICES:
                display.append(row)
            if issues and len(mismatches) < 12:
                mismatches.append(row)
    return {
        "passed": not blockers and not failures,
        "blockers": blockers,
        "checks": {grain: {"groups": checks[grain], "failed": failures[grain]} for grain in GRAINS},
        "rows": display,
        "mismatches": mismatches,
        "source": report_view(source),
        "candidate": report_view(candidate),
    }
