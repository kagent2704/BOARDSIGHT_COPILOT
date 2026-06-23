from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from boardsight_ai.database import execute, fetchone, is_postgres, table_columns


def init_auth_storage(database_path: Path) -> None:
    if is_postgres(database_path):
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'analyst',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    else:
        execute(
            database_path,
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
            """,
        )
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )

    existing_columns = table_columns(database_path, "users")
    if "display_name" not in existing_columns:
        execute(database_path, "ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT 'BoardSight User'")
    if "email" not in existing_columns:
        execute(database_path, "ALTER TABLE users ADD COLUMN email TEXT")
    execute(
        database_path,
        """
        UPDATE users
        SET email = LOWER(username || '@boardsight.local')
        WHERE email IS NULL OR TRIM(email) = ''
        """,
    )
    execute(database_path, "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    session_columns = table_columns(database_path, "sessions")
    if "user_id" not in session_columns:
        execute(
            database_path,
            "ALTER TABLE sessions ADD COLUMN user_id " + ("BIGINT DEFAULT 0" if is_postgres(database_path) else "INTEGER DEFAULT 0"),
        )


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
    insert_sql = """
        INSERT INTO users (username, email, display_name, password_hash, role)
        VALUES (:username, :email, :display_name, :password_hash, :role)
    """
    if is_postgres(database_path):
        insert_sql += " ON CONFLICT (username) DO NOTHING"
    else:
        insert_sql = insert_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
    before = fetchone(database_path, "SELECT id FROM users WHERE LOWER(username) = LOWER(:username)", {"username": username})
    execute(
        database_path,
        insert_sql,
        {
            "username": username,
            "email": resolved_email,
            "display_name": resolved_display_name,
            "password_hash": hash_password(password),
            "role": role,
        },
    )
    after = fetchone(database_path, "SELECT id FROM users WHERE LOWER(username) = LOWER(:username)", {"username": username})
    return before is None and after is not None


def authenticate_user(database_path: Path, identifier: str, password: str) -> dict | None:
    init_auth_storage(database_path)
    resolved_identifier = identifier.strip().lower()
    row = fetchone(
        database_path,
        """
        SELECT id, username, email, display_name, role
        FROM users
        WHERE (LOWER(username) = :identifier OR LOWER(email) = :identifier) AND password_hash = :password_hash
        """,
        {"identifier": resolved_identifier, "password_hash": hash_password(password)},
    )
    if row is None:
        return None
    token = secrets.token_hex(16)
    execute(
        database_path,
        "INSERT INTO sessions (token, user_id, username) VALUES (:token, :user_id, :username)",
        {"token": token, "user_id": int(row["id"]), "username": row["username"]},
    )
    return {
        "token": token,
        "user_id": int(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
    }


def get_session_user(database_path: Path, token: str) -> dict | None:
    init_auth_storage(database_path)
    row = fetchone(
        database_path,
        """
        SELECT u.id, u.username, u.email, u.display_name, u.role
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = :token
        """,
        {"token": token},
    )
    if row is None:
        return None
    return {
        "user_id": int(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
    }


def get_user_by_username(database_path: Path, username: str) -> dict | None:
    init_auth_storage(database_path)
    row = fetchone(
        database_path,
        """
        SELECT id, username, email, display_name, role
        FROM users
        WHERE LOWER(username) = LOWER(:username)
        """,
        {"username": username},
    )
    if row is None:
        return None
    return {
        "user_id": int(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
    }
