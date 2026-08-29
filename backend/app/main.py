"""FastAPI application: dataset upload, run creation, and progress/report
retrieval.

Pipeline execution is synchronous within the POST /api/runs request in
this implementation — acceptable for the small, hackathon-scale datasets
in datasets/, and it avoids the added complexity of background-task/DB
thread-safety for a demo. A production version would move this to a
background job queue; that tradeoff is recorded in docs/limitations.md.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.llm.client import LLMClient
from app.orchestrator import run_full_pipeline
from app.profiling.profiler import build_dataset_profile, load_dataset
from app.storage.db import Dataset, Run, StageResult, get_session

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"

# Frontend dev server origin(s), comma-separated via CORS_ORIGINS. Without
# this, every browser request from the Next.js app is silently blocked by
# CORS while curl/pytest (which don't enforce it) keep working — exactly
# the kind of failure that only shows up once someone opens dev tools.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_cors_origins = os.environ.get("CORS_ORIGINS", _default_origins).split(",")

app = FastAPI(title="InsightForge API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_llm_client() -> LLMClient:
    return LLMClient()


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


@app.post("/api/datasets")
async def upload_dataset(file: UploadFile = File(...), session: Session = Depends(get_session)):
    dataset_id = uuid.uuid4().hex[:12]
    dataset_dir = UPLOAD_DIR / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    try:
        df = load_dataset(file_path)
    except (ValueError, pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not read dataset: {exc}") from exc
    profile = build_dataset_profile(df, dataset_name=file.filename)

    session.add(Dataset(id=dataset_id, filename=file.filename, file_path=str(file_path)))
    session.commit()

    return {"dataset_id": dataset_id, "profile": profile.model_dump()}


@app.post("/api/runs")
def create_run(
    dataset_id: str,
    question: str,
    session: Session = Depends(get_session),
    llm_client: LLMClient = Depends(get_llm_client),
):
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    run_id = uuid.uuid4().hex[:12]
    run = Run(id=run_id, dataset_name=dataset.filename, question=question, status="RUNNING")
    session.add(run)
    session.commit()

    def persist_stage(stage_name: str, payload: Any) -> None:
        if isinstance(payload, list):
            payload_json = json.dumps([_to_jsonable(p) for p in payload])
        else:
            payload_json = json.dumps(_to_jsonable(payload))
        session.add(StageResult(run_id=run_id, stage_name=stage_name, payload_json=payload_json))
        session.commit()

    try:
        df = load_dataset(dataset.file_path)
        result = run_full_pipeline(
            df, question, llm_client, dataset_name=dataset.filename, on_stage=persist_stage
        )
        run.status = "COMPLETED"
        session.add(run)
        session.commit()
        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "report": result.report.model_dump() if result.report else None,
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the client, run marked FAILED either way
        run.status = "FAILED"
        run.error = str(exc)
        session.add(run)
        session.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/runs")
def list_runs(session: Session = Depends(get_session)):
    runs = session.exec(select(Run).order_by(Run.created_at.desc())).all()
    return [
        {
            "run_id": r.id,
            "status": r.status,
            "question": r.question,
            "dataset_name": r.dataset_name,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    stages = session.exec(select(StageResult).where(StageResult.run_id == run_id)).all()
    return {
        "run_id": run.id,
        "status": run.status,
        "error": run.error,
        "question": run.question,
        "dataset_name": run.dataset_name,
        "stages": [{"stage_name": s.stage_name, "payload": json.loads(s.payload_json)} for s in stages],
    }
