from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from migration_rehearsal.api import create_app
from migration_rehearsal.comparison import compare
from migration_rehearsal.inputs import Inputs
from migration_rehearsal.providers import ProviderError
from migration_rehearsal.workflow import Rehearsal
from scripts.verify import locate, verify


@pytest.fixture
def lab():
    return Rehearsal(Inputs("fixture"))


@pytest.fixture
def client(lab):
    with TestClient(create_app(lab)) as api:
        yield api


def action(client, path, code=200, **payload):
    version = client.get("/api/state").json()["version"]
    response = client.post(f"/api/{path}", json={"version": version, **payload})
    assert response.status_code == code, response.json()
    return response.json()


def select(client, *, scenario="clean", target="local", batch="current"):
    return action(client, "selection", scenario=scenario, target=target, batch=batch)


def approved(client):
    select(client)
    state = action(client, "check")
    assert state["phase"] == "approved"
    return state


def test_fixture_business_acceptance():
    result = verify("fixture", "local")
    assert result["results"]["active_read"]["served"]["backend"] == "DuckDB candidate"


def test_half_open_dates_and_null_unknown_zones(lab):
    old = lab.source.read("current")
    comp = compare(old, lab.provider.read("current"), old.batch, lab.inputs.zones)
    assert comp["passed"]
    december = locate(comp, "month", month="2024-12-01")
    assert december["old"] == {
        "trips": 2, "fee_cents": None, "has_fee": 0, "negative_fees": 0, "null_fees": 0, "present_fees": 0
    }
    january = locate(comp, "month")
    assert january["old"] == {
        "trips": 10, "fee_cents": 950, "has_fee": 1, "negative_fees": 1, "null_fees": 1, "present_fees": 9
    }
    daily = {row["pickup_day"]: row for row in old.rows if row["grain"] == "day"}
    assert set(daily) == {"2024-12-01", "2024-12-31", "2025-01-01", "2025-01-06", "2025-01-07", "2025-01-31"}
    assert daily["2025-01-01"]["fee_cents"] == 75
    assert daily["2025-01-07"]["trips"] == 2
    unknown = locate(comp, "zone", day="2025-01-06", zone=900)
    assert unknown["zone_name"] == "Unknown zone 900" and unknown["old"]["fee_cents"] is None
    missing = locate(comp, "zone", day="2025-01-06")
    assert missing["zone_name"] == "Missing pickup zone" and missing["old"]["fee_cents"] == 0


def test_duplicate_and_missing_keys_fail(lab):
    source = lab.source.read("current")
    target = lab.provider.read("current")
    index = next(i for i, row in enumerate(target.rows) if row["grain"] == "zone")
    missing = target.rows.pop(index)
    target.rows += [target.rows[0], dict(missing, zone=12345)]
    result = compare(source, target, source.batch, lab.inputs.zones)
    assert not result["passed"]
    assert "duplicate report keys" in result["blockers"][0]
    assert {row["issues"][0] for row in result["mismatches"]} == {"Missing candidate key", "Extra candidate key"}


@pytest.mark.parametrize("change", [
    {"batch": "december"}, {"target": "bigquery"}, {"scenario": "swap"},
])
def test_changed_selection_invalidates_approval(client, change):
    state = approved(client)
    changed = select(client, **change)
    assert changed["approval"] is None
    action(client, "switch", 409, approval=state["approval"])
    assert client.get("/api/state").json()["report"]["backend"] == "DuckDB source"


def test_revision_change_invalidates_approval(client, monkeypatch):
    state = approved(client)
    monkeypatch.setattr("migration_rehearsal.workflow.report_revision", lambda _: "new revision")
    action(client, "switch", 409, approval=state["approval"])


def test_switch_requires_same_query_result(lab, client, monkeypatch):
    state = approved(client)
    read = lab.provider.read

    def changed(*args):
        result = read(*args)
        result.rows[0]["pickup_clock_sum"] += 1
        return result

    monkeypatch.setattr(lab.provider, "read", changed)
    blocked = action(client, "switch", approval=state["approval"])
    assert blocked["phase"] == "pending"
    assert blocked["report"]["backend"] == "DuckDB source"


def test_repeat_and_overlap_are_rejected(lab, client, monkeypatch):
    state = approved(client)
    read = lab.provider.read
    entered, release = Event(), Event()

    def blocked_read(*args):
        entered.set()
        assert release.wait(10)
        return read(*args)

    monkeypatch.setattr(lab.provider, "read", blocked_read)
    body = {"version": state["version"], "approval": state["approval"]}
    with ThreadPoolExecutor() as pool:
        first = pool.submit(client.post, "/api/switch", json=body)
        try:
            assert entered.wait(10)
            assert client.post("/api/switch", json=body).status_code == 409
        finally:
            release.set()
        assert first.result(timeout=10).json()["phase"] == "switched"
    assert client.post("/api/switch", json=body).status_code == 409
    action(client, "switch", 409, approval=state["approval"])


def test_observed_provider_failure_is_distinct(lab, client, monkeypatch):
    state = approved(client)
    action(client, "switch", approval=state["approval"])

    def fail(*_):
        raise ProviderError("Provider query timed out.")

    monkeypatch.setattr(lab.provider, "read", fail)
    recovered = action(client, "report")
    assert recovered["recovery"]["kind"] == "Observed"
    assert recovered["phase"] == "fallback"


def test_live_target_on_fixture_is_pending(client):
    select(client, target="databricks")
    state = action(client, "check")
    assert state["phase"] == "pending"
    assert state["comparison"] is None and state["approval"] is None
    action(client, "switch", 409, approval="arbitrary")


def test_selection_validation(client):
    action(client, "selection", 422, target="arbitrary", scenario="clean", batch="current")
    action(client, "failure", 409)
