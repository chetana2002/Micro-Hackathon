"""SQLite-backed persistence for Dataset/Run/StageResult records via
SQLModel — no external database service required, which is what keeps
docs/reproduction.md to `pip install` + `npm install` with nothing else to
stand up.

The engine is created lazily and cached per DATABASE_URL (rather than at
import time) so tests can point at an isolated file without any import-time
side effect on the default dev database file.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

_DEFAULT_DB_URL = "sqlite:///./backend/data/insightforge.db"
_engine_cache: dict = {}


class Dataset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    filename: str
    file_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True)
    dataset_name: str
    question: str
    status: str = "PENDING"  # PENDING | RUNNING | COMPLETED | FAILED
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StageResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id")
    stage_name: str
    payload_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def get_engine():
    url = os.environ.get("DATABASE_URL", _DEFAULT_DB_URL)
    if url not in _engine_cache:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine = create_engine(url, connect_args=connect_args)
        SQLModel.metadata.create_all(engine)
        _engine_cache[url] = engine
    return _engine_cache[url]


def get_session():
    with Session(get_engine()) as session:
        yield session
