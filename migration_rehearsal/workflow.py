from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .comparison import compare, report_digest, report_view, shape_errors
from .inputs import BRAND, Inputs
from .providers import BigQuery, Databricks, DuckDB, ProviderError, Report
from .query import report_revision

SCENARIOS = {
    "swap": "Midtown fee swap",
    "clean": "Corrected report",
    "wrong_day": "Fees on the wrong day",
    "stale": "Stale candidate",
}


class Conflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Approval:
    token: str
    selection: tuple[str, str, str]
    revision: str
    source_digest: str
    candidate_digest: str


class Rehearsal:
    def __init__(self, inputs: Inputs, default_target: str = "local"):
        self.inputs = inputs
        self.source = DuckDB(inputs, "DuckDB source")
        self.providers = {
            "local": DuckDB(inputs, "DuckDB candidate"),
            "databricks": Databricks(inputs),
            "bigquery": BigQuery(inputs),
        }
        self.default_target = default_target
        self.lock = threading.Lock()
        self.version = 0
        self.reset()

    def reset(self) -> None:
        source = self.source.read("current")
        self.target, self.scenario, self.batch = self.default_target, "swap", "current"
        self.phase = "ready"
        self.approval = None
        self.comparison = None
        self.events = []
        self.recovery = None
        self.detail = "Run checks to compare the source and selected candidate."
        self.served = source
        self.record("Source served", self.served)

    def record(self, label: str, report: Report | None = None, note: str = "") -> None:
        self.events.append({
            "label": label,
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "backend": report.backend if report else None,
            "batch": report.batch["name"] if report else None,
            "revision": report.revision if report else None,
            "note": note,
        })
        self.events = self.events[-20:]

    @property
    def selection(self) -> tuple[str, str, str]:
        return self.target, self.scenario, self.batch

    @property
    def provider(self):
        return self.providers[self.target]

    def select(self, target: str, scenario: str, batch: str) -> None:
        if self.phase in ("switched", "fallback", "unavailable"):
            raise Conflict("Reset before changing the active rehearsal.")
        if self.selection == (target, scenario, batch):
            return
        self.served = self.source.read(batch)
        self.target, self.scenario, self.batch = target, scenario, batch
        self.approval = None
        self.comparison = None
        self.phase = "ready"
        self.detail = "Selection changed. Run fresh checks."
        self.record("Selection changed", self.served, SCENARIOS[scenario])

    def checks(self) -> None:
        if self.phase in ("switched", "fallback", "unavailable"):
            raise Conflict("Reset before running another comparison.")
        self.approval = None
        self.comparison = None
        if self.target != "local" and self.inputs.mode != "full":
            self.phase = "pending"
            self.detail = "Live targets require the verified TLC files. Start in full-data mode."
            self.record("Live check pending", note=self.detail)
            return
        try:
            source = self.source.read(self.batch)
            candidate_batch = "december" if self.scenario == "stale" else self.batch
            candidate = self.provider.read(candidate_batch, self.scenario)
        except ProviderError as error:
            self.phase = "pending"
            self.detail = str(error)
            self.record("Check could not run", note=self.detail)
            return
        self.served = source
        self.comparison = compare(source, candidate, self.inputs.identity(self.batch), self.inputs.zones)
        if self.comparison["passed"]:
            self.phase = "approved"
            self.detail = "All checks passed. The old system will serve until you approve the switch."
            self.approval = Approval(secrets.token_urlsafe(24), self.selection, candidate.revision,
                                     report_digest(source), report_digest(candidate))
            self.record("Checks passed", candidate)
        else:
            self.phase = "blocked"
            self.detail = self.blocked_reason()
            self.record("Switch blocked", candidate, self.detail)

    def blocked_reason(self) -> str:
        if self.comparison["blockers"]:
            return self.comparison["blockers"][0]
        if self.scenario == "swap":
            return "The daily totals agree, but both Midtown zones have the wrong recorded fees."
        if self.scenario == "wrong_day":
            return "January’s total agrees, but recorded fees moved from January 6 to January 7."
        return "The candidate differs from the old system. Review the failed checks."

    def switch(self, token: str) -> None:
        approval = self.approval
        if (self.phase != "approved" or approval is None or approval.token != token
                or approval.selection != self.selection or approval.revision != report_revision(self.scenario)):
            raise Conflict("A current passing check is required before switching.")
        try:
            source = self.source.read(self.batch)
            candidate = self.provider.read(self.batch, self.scenario)
            if report_digest(source) != approval.source_digest or report_digest(candidate) != approval.candidate_digest:
                raise ProviderError("The checked input or report changed. Run fresh checks.")
        except ProviderError as error:
            self.approval = None
            self.comparison = None
            self.phase = "pending"
            self.detail = str(error)
            self.record("Switch held", note=self.detail)
            return
        self.served = candidate
        self.phase = "switched"
        self.detail = f"{candidate.backend} returned the approved report."
        self.record("Switch approved and report served", candidate)

    def read(self, injection: str = "none") -> None:
        if self.phase != "switched":
            if injection != "none":
                raise Conflict("Switch and serve a candidate report before injecting a query failure.")
            if self.phase == "unavailable":
                raise Conflict("Reset the rehearsal to retry after an unavailable report.")
            try:
                result = self.source.read(self.batch)
                if shape_errors(result, self.inputs.identity(self.batch)):
                    raise ProviderError("The source returned an unverified batch.")
                if self.phase == "fallback" and report_digest(result) != self.approval.source_digest:
                    raise ProviderError("The source no longer matches the verified report.")
                self.served = result
                self.record("Source report refreshed", self.served)
            except ProviderError as error:
                self.served = None
                self.approval = None
                self.phase = "unavailable"
                self.detail = str(error)
                self.record("Report unavailable", note=self.detail)
            return
        try:
            if injection != "none":
                raise ProviderError("Simulated candidate query failure.")
            result = self.provider.read(self.batch, self.scenario)
            if report_digest(result) != self.approval.candidate_digest:
                raise ProviderError("The candidate no longer matches the approved report.")
            self.served = result
            self.record("Active report refreshed", result)
        except ProviderError as error:
            failed_at = time.monotonic_ns()
            self.fallback(failed_at, str(error), injection)

    def fallback(self, failed_at: int, reason: str, injection: str) -> None:
        kind = "Simulated" if injection != "none" else "Observed"
        self.record(f"{kind} query failure", note=f"{self.provider.name} · {reason}")
        self.recovery = {"kind": kind, "reason": reason, "milliseconds": None, "batch": None}
        try:
            if injection == "unavailable":
                raise ProviderError("Simulated source query failure.")
            result = self.source.read("december" if injection == "stale" else self.batch)
            if shape_errors(result, self.inputs.identity(self.batch)):
                raise ProviderError("The fallback source did not return the current verified batch.")
            if report_digest(result) != self.approval.source_digest:
                raise ProviderError("The fallback source no longer matches the verified report.")
            elapsed = (time.monotonic_ns() - failed_at) / 1_000_000
        except ProviderError as error:
            self.phase = "unavailable"
            self.served = None
            self.detail = str(error)
            self.record("Report unavailable", note=self.detail)
            return
        self.phase = "fallback"
        self.served = result
        self.recovery.update(milliseconds=round(elapsed, 2), batch=result.batch["name"])
        self.detail = "The old system returned the current verified report."
        self.record("Fallback report served", result, f"{elapsed:.2f} ms from detected failure")

    def snapshot(self) -> dict:
        return {
            "brand": BRAND,
            "version": self.version,
            "mode": self.inputs.mode,
            "target": self.target,
            "targets": {key: provider.name for key, provider in self.providers.items()},
            "scenario": self.scenario,
            "scenarios": SCENARIOS,
            "batch": self.inputs.identity(self.batch),
            "phase": self.phase,
            "detail": self.detail,
            "approval": self.approval.token if self.phase == "approved" else None,
            "comparison": self.comparison,
            "report": report_view(self.served),
            "recovery": self.recovery,
            "events": self.events.copy(),
        }
