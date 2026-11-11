"""Run the business acceptance sequence against the actual FastAPI routes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from migration_rehearsal.api import create_app
from migration_rehearsal.config import configure
from migration_rehearsal.inputs import BRAND, Inputs
from migration_rehearsal.workflow import Rehearsal

FULL = {
    "december": (3_668_337, None), "january": (3_475_204, 167_995_575),
    "jan6": (80_126, 3_883_125), "jan7": (100_643, 5_205_225),
    "zone161": (4_342, 307_725), "zone162": (3_217, 226_425),
}
FIXTURE = {
    "december": (2, None), "january": (10, 950), "jan6": (6, 425),
    "jan7": (2, 375), "zone161": (3, 300), "zone162": (1, 125),
}


def locate(comp: dict, grain: str, *, day=None, zone=None, month="2025-01-01") -> dict:
    return next(row for row in comp["rows"] if (
        row["grain"], row["day"], row["zone"], row["month"]
    ) == (grain, day, zone, month))


def actual(row: dict, side: str = "old") -> tuple:
    value = row[side]
    return value["trips"], value["fee_cents"]


def record(state: dict) -> dict:
    comp = state["comparison"]
    return {
        "phase": state["phase"],
        "reason": state["detail"],
        "expected_batch": state["batch"]["name"],
        "source": comp["source"] if comp else None,
        "candidate": comp["candidate"] if comp else None,
        "served": state["report"],
        "checks": comp["checks"] if comp else None,
        "blockers": comp["blockers"] if comp else [],
        "mismatches": comp["mismatches"] if comp else [],
        "recovery": state["recovery"],
        "last_event": state["events"][-1],
    }


def verify(mode: str, target: str) -> dict:
    configure()
    lab = Rehearsal(Inputs(mode), target)
    expected = FULL if mode == "full" else FIXTURE
    smoke = lab.providers[target].smoke()
    assert smoke == 1
    with TestClient(create_app(lab)) as client:
        state = client.get("/api/state").json()

        def action(path: str, status: int = 200, **data) -> dict:
            nonlocal state
            response = client.post("/api/" + path, json={"version": state["version"], **data})
            assert response.status_code == status, (path, response.status_code, response.json())
            if status == 200:
                state = response.json()
                print(target, path, state["phase"], state["detail"], flush=True)
            return state

        def select(scenario: str, batch: str = "current") -> None:
            action("selection", target=target, scenario=scenario, batch=batch)

        results = {}
        swap = action("check")
        assert swap["phase"] == "blocked", swap["detail"]
        comp = swap["comparison"]
        rows = {
            "december": locate(comp, "month", month="2024-12-01"),
            "january": locate(comp, "month"),
            "jan6": locate(comp, "day", day="2025-01-06"),
            "jan7": locate(comp, "day", day="2025-01-07"),
            "zone161": locate(comp, "zone", day="2025-01-06", zone=161),
            "zone162": locate(comp, "zone", day="2025-01-06", zone=162),
        }
        assert {key: actual(row) for key, row in rows.items()} == expected
        assert all(actual(rows[key], "candidate") == expected[key] for key in ("december", "january", "jan6", "jan7"))
        difference = expected["zone161"][1] - expected["zone162"][1]
        assert (rows["zone161"]["fee_difference"], rows["zone162"]["fee_difference"]) == (-difference, difference)
        assert rows["zone161"]["trip_difference"] == rows["zone162"]["trip_difference"] == 0
        assert comp["checks"]["zone"]["failed"] == 2
        assert comp["checks"]["month"]["failed"] == comp["checks"]["day"]["failed"] == 0
        assert rows["december"]["old"]["has_fee"] == rows["december"]["candidate"]["has_fee"] == 0
        assert rows["january"]["old"]["negative_fees"] == (6553 if mode == "full" else 1)
        assert rows["january"]["old"]["null_fees"] == (0 if mode == "full" else 1)
        action("switch", status=409, approval="blocked")
        results["zone_swap"] = record(swap)

        select("wrong_day")
        wrong = action("check")
        assert wrong["phase"] == "blocked", wrong["detail"]
        comp = wrong["comparison"]
        assert comp["checks"]["month"]["failed"] == 0 and comp["checks"]["day"]["failed"] == 2
        assert locate(comp, "day", day="2025-01-06")["fee_difference"] == -expected["jan6"][1]
        assert locate(comp, "day", day="2025-01-07")["fee_difference"] == expected["jan6"][1]
        results["wrong_day"] = record(wrong)

        select("stale")
        stale = action("check")
        assert stale["phase"] == "blocked" and stale["comparison"]["candidate"]["batch"]["name"] == "december"
        results["stale_candidate"] = record(stale)

        select("clean")
        passed = action("check")
        assert passed["phase"] == "approved", passed["detail"]
        assert passed["report"]["backend"] == "DuckDB source"
        approval = passed["approval"]
        select("clean", "december")
        action("switch", status=409, approval=approval)
        results["stale_approval"] = {"old_approval_rejected": True, "changed_batch": "december"}

        select("clean")
        passed = action("check")
        assert passed["phase"] == "approved", passed["detail"]
        results["corrected"] = record(passed)
        switched = action("switch", approval=passed["approval"])
        assert switched["phase"] == "switched", switched["detail"]
        assert switched["report"]["backend"] == lab.providers[target].name
        assert switched["report"]["live"] == (target != "local")
        assert switched["report"]["focus"]["2025-01-06"]["fee_cents"] == expected["jan6"][1]
        refreshed = action("report")
        assert refreshed["events"][-1]["label"] == "Active report refreshed", refreshed["recovery"]
        results["active_read"] = record(refreshed)

        recovered = action("failure")
        assert recovered["phase"] == "fallback", recovered["detail"]
        assert recovered["report"]["backend"] == "DuckDB source"
        assert recovered["recovery"]["batch"] == "current"
        assert recovered["recovery"]["milliseconds"] > 0
        results["recovery"] = record(recovered)

        for injection in ("stale", "unavailable"):
            action("reset")
            select("clean")
            passed = action("check")
            assert passed["phase"] == "approved", passed["detail"]
            action("switch", approval=passed["approval"])
            failed = action("failure", injection=injection)
            assert failed["phase"] == "unavailable" and failed["report"] is None
            assert failed["recovery"]["milliseconds"] is None
            results["fallback_" + injection] = record(failed)

    return {
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_mode": "Live warehouse" if target != "local" else "Local rehearsal",
        "data": mode, "target": lab.providers[target].name, "select_1": smoke,
        "batch": lab.inputs.identity("current"), "baseline": rows,
        "results": results,
    }


def markdown(evidence: dict) -> str:
    def cash(value: int | None) -> str:
        return "Unavailable" if value is None else ("−" if value < 0 else "") + f"${abs(value) / 100:,.2f}"

    lines = [
        f"# {BRAND['name']} · {evidence['target']} results",
        "",
        f"Observed at {evidence['observed_at']} UTC. {evidence['run_mode']} using {evidence['data']} inputs.",
        f"Connector smoke result `SELECT 1 → {evidence['select_1']}`.",
        "",
        "| Slice | Old trips | Candidate trips | Old recorded fee | Candidate recorded fee | Difference |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    names = {"december": "December", "january": "January", "jan6": "Jan 6", "jan7": "Jan 7",
             "zone161": "Jan 6 · Midtown Center (161)", "zone162": "Jan 6 · Midtown East (162)"}
    for label, row in evidence["baseline"].items():
        old, candidate = row["old"], row["candidate"]
        lines.append(f"| {names[label]} | {old['trips']:,} | {candidate['trips']:,} | "
                     f"{cash(old['fee_cents'])} | {cash(candidate['fee_cents'])} | {cash(row['fee_difference'])} |")
    lines += ["", "| Scenario | Outcome | Returned backend and batch | Recovery |",
              "| --- | --- | --- | ---: |"]
    for label, record in evidence["results"].items():
        report = record.get("served")
        recovery = record.get("recovery")
        served = f"{report['backend']} · {report['batch']['name']}" if report else "—"
        elapsed = f"{recovery['milliseconds']:.2f} ms" if recovery and recovery["milliseconds"] is not None else "—"
        status = record.get("phase", "Old approval rejected (HTTP 409)")
        lines.append(f"| {label.replace('_', ' ').capitalize()} | {status} | {served} | {elapsed} |")
    lines += ["", "Recovery is measured from the detected candidate failure to the first source result "
              "that passes the batch and report digest checks. The injected failure bypasses provider transport.", "",
              "The matching reports compare input fingerprints, key coverage, signed fees and civil pickup "
              "clock checks, including the minimum and maximum pickup second for every group.",
              "The JSON companion includes full input hashes and report revisions.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("full", "fixture"), default="full")
    parser.add_argument("--target", choices=("local", "databricks", "bigquery"), default="local")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.target != "local" and args.mode != "full":
        parser.error("Live warehouse verification requires full data.")
    evidence = verify(args.mode, args.target)
    if args.output:
        args.output.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n")
        args.output.with_suffix(".md").write_text(markdown(evidence))
    else:
        print(markdown(evidence))


if __name__ == "__main__":
    main()
