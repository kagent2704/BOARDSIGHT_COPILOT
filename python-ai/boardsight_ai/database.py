from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

_ENGINE_CACHE: dict[str, Engine] = {}


def configured_database_url() -> str | None:
    value = os.getenv("BOARDSIGHT_DATABASE_URL", "").strip()
    return value or None


def resolve_database_url(database_path: Path) -> str:
    configured = configured_database_url()
    if configured:
        return configured
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path}"


def get_engine(database_path: Path) -> Engine:
    url = resolve_database_url(database_path)
    if url not in _ENGINE_CACHE:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite:///") else {}
        _ENGINE_CACHE[url] = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    return _ENGINE_CACHE[url]


def is_postgres(database_path: Path) -> bool:
    return get_engine(database_path).dialect.name.startswith("postgres")


def table_columns(database_path: Path, table_name: str) -> set[str]:
    inspector = inspect(get_engine(database_path))
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def execute(database_path: Path, sql: str, params: dict[str, Any] | None = None) -> None:
    engine = get_engine(database_path)
    with engine.begin() as connection:
        connection.execute(text(sql), params or {})


def fetchone(database_path: Path, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    engine = get_engine(database_path)
    with engine.begin() as connection:
        row = connection.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def fetchall(database_path: Path, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    engine = get_engine(database_path)
    with engine.begin() as connection:
        rows = connection.execute(text(sql), params or {}).mappings().all()
    return [dict(row) for row in rows]


def insert_and_return_id(
    database_path: Path,
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    id_column: str = "id",
) -> int:
    engine = get_engine(database_path)
    dialect = engine.dialect.name
    statement = sql
    if dialect.startswith("postgres") and "RETURNING" not in sql.upper():
        statement = f"{sql.rstrip().rstrip(';')} RETURNING {id_column}"
    with engine.begin() as connection:
        result = connection.execute(text(statement), params or {})
        if dialect.startswith("postgres"):
            inserted_id = result.scalar_one()
        else:
            inserted_id = result.lastrowid
    return int(inserted_id)
