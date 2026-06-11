from __future__ import annotations

import hashlib
import secrets
import sqlite3
from pathlib import Path


def init_auth_storage(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'analyst',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "display_name" not in existing_columns:
            connection.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT 'BoardSight User'")
        if "email" not in existing_columns:
            connection.execute("ALTER TABLE users ADD COLUMN email TEXT")
        connection.execute(
            """
            UPDATE users
            SET email = LOWER(username || '@boardsight.local')
            WHERE email IS NULL OR TRIM(email) = ''
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )

        session_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "user_id" not in session_columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER DEFAULT 0")

        connection.commit()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_user(
    database_path: Path,
    username: str,
    password: str,
    role: str = "analyst",
    display_name: str | None = None,
    email: str | None = None,
) -> bool:
    init_auth_storage(database_path)
    resolved_display_name = (display_name or username).strip() or username
    resolved_email = (email or f"{username}@boardsight.local").strip().lower()
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO users (username, email, display_name, password_hash, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, resolved_email, resolved_display_name, hash_password(password), role),
        )
        connection.commit()
        return int(cursor.rowcount or 0) > 0


def authenticate_user(database_path: Path, identifier: str, password: str) -> dict | None:
    init_auth_storage(database_path)
    resolved_identifier = identifier.strip().lower()
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, username, email, display_name, role
            FROM users
            WHERE (LOWER(username) = ? OR LOWER(email) = ?) AND password_hash = ?
            """,
            (resolved_identifier, resolved_identifier, hash_password(password)),
        ).fetchone()
        if row is None:
            return None
        token = secrets.token_hex(16)
        connection.execute(
            "INSERT INTO sessions (token, user_id, username) VALUES (?, ?, ?)",
            (token, int(row[0]), row[1]),
        )
        connection.commit()
        return {
            "token": token,
            "user_id": int(row[0]),
            "username": row[1],
            "email": row[2],
            "display_name": row[3],
            "role": row[4],
        }


def get_session_user(database_path: Path, token: str) -> dict | None:
    init_auth_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT u.id, u.username, u.email, u.display_name, u.role
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if row is None:
        return None
    return {
        "user_id": int(row[0]),
        "username": row[1],
        "email": row[2],
        "display_name": row[3],
        "role": row[4],
    }


def get_user_by_username(database_path: Path, username: str) -> dict | None:
    init_auth_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, username, email, display_name, role
            FROM users
            WHERE LOWER(username) = LOWER(?)
            """,
            (username,),
        ).fetchone()
    if row is None:
        return None
    return {
        "user_id": int(row[0]),
        "username": row[1],
        "email": row[2],
        "display_name": row[3],
        "role": row[4],
    }
