from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import configure
from .inputs import ROOT, Inputs
from .providers import ProviderError
from .workflow import Conflict, Rehearsal

Target = Literal["local", "databricks", "bigquery"]
Scenario = Literal["swap", "clean", "wrong_day", "stale"]
Batch = Literal["december", "current"]
Injection = Literal["candidate", "stale", "unavailable"]


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)


class Selection(Action):
    target: Target
    scenario: Scenario
    batch: Batch


class Switch(Action):
    approval: str = Field(min_length=1, max_length=100)


class Failure(Action):
    injection: Injection = "candidate"


def create_app(rehearsal: Rehearsal | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if rehearsal is None:
            configure()
            mode = os.getenv("REHEARSAL_DATA", "fixture")
            target = os.getenv("REHEARSAL_TARGET", "local")
            if mode not in ("fixture", "full") or target not in ("local", "databricks", "bigquery"):
                raise ValueError("Use fixture/full data and local/databricks/bigquery target.")
            app.state.rehearsal = Rehearsal(Inputs(mode), target)
        else:
            app.state.rehearsal = rehearsal
        yield

    app = FastAPI(lifespan=lifespan, title="Migration Rehearsal API")

    def mutate(action: Action, callback):
        lab = app.state.rehearsal
        if not lab.lock.acquire(blocking=False):
            raise HTTPException(409, "An action is already in progress.")
        try:
            if action.version != lab.version:
                raise Conflict("The rehearsal changed. Refresh and try again.")
            callback(lab)
            lab.version += 1
            return lab.snapshot()
        except Conflict as error:
            raise HTTPException(409, str(error)) from None
        except ProviderError as error:
            raise HTTPException(503, str(error)) from None
        finally:
            lab.lock.release()

    @app.get("/api/state")
    def state():
        lab = app.state.rehearsal
        with lab.lock:
            return lab.snapshot()

    @app.post("/api/selection")
    def selection(body: Selection):
        return mutate(body, lambda lab: lab.select(body.target, body.scenario, body.batch))

    @app.post("/api/check")
    def check(body: Action):
        return mutate(body, lambda lab: lab.checks())

    @app.post("/api/switch")
    def switch(body: Switch):
        return mutate(body, lambda lab: lab.switch(body.approval))

    @app.post("/api/report")
    def report(body: Action):
        return mutate(body, lambda lab: lab.read())

    @app.post("/api/failure")
    def failure(body: Failure):
        return mutate(body, lambda lab: lab.read(body.injection))

    @app.post("/api/reset")
    def reset(body: Action):
        return mutate(body, lambda lab: lab.reset())

    dist = ROOT / "frontend/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend():
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(503, "Build the frontend with npm ci and npm run build in frontend/.")
        return FileResponse(index)

    return app


app = create_app()
