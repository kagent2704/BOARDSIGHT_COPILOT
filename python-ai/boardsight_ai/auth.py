from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from boardsight_ai.database import execute, fetchone, is_postgres, table_columns


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.getenv(name, str(default))).strip()
    try:
        return max(1, int(raw_value))
    except ValueError:
        return default


PASSWORD_HASHER = PasswordHasher(
    time_cost=_env_int("BOARDSIGHT_ARGON2_TIME_COST", 2),
    memory_cost=_env_int("BOARDSIGHT_ARGON2_MEMORY_COST", 19456),
    parallelism=_env_int("BOARDSIGHT_ARGON2_PARALLELISM", 1),
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00").replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def session_ttl_seconds() -> int:
    return max(300, int(os.getenv("BOARDSIGHT_SESSION_TTL_SECONDS", "604800")))


def verification_ttl_seconds() -> int:
    return max(300, int(os.getenv("BOARDSIGHT_EMAIL_VERIFICATION_TTL_SECONDS", "86400")))


def init_auth_storage(database_path: Path) -> None:
    bool_type = "BOOLEAN" if is_postgres(database_path) else "INTEGER"
    timestamp_type = "TIMESTAMP" if is_postgres(database_path) else "TEXT"
    true_literal = "TRUE" if is_postgres(database_path) else "1"

    if is_postgres(database_path):
        execute(
            database_path,
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'analyst',
                email_verified {bool_type} NOT NULL DEFAULT {true_literal},
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        execute(
            database_path,
            f"""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at {timestamp_type},
                revoked_at {timestamp_type}
            )
            """,
        )
        execute(
            database_path,
            f"""
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                email TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at {timestamp_type} NOT NULL,
                consumed_at {timestamp_type}
            )
            """,
        )
    else:
        execute(
            database_path,
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'analyst',
                email_verified {bool_type} NOT NULL DEFAULT {true_literal},
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        execute(
            database_path,
            f"""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at {timestamp_type},
                revoked_at {timestamp_type}
            )
            """,
        )
        execute(
            database_path,
            f"""
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at {timestamp_type} NOT NULL,
                consumed_at {timestamp_type}
            )
            """,
        )

    existing_columns = table_columns(database_path, "users")
    if "display_name" not in existing_columns:
        execute(database_path, "ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT 'BoardSight User'")
    if "email" not in existing_columns:
        execute(database_path, "ALTER TABLE users ADD COLUMN email TEXT")
    if "email_verified" not in existing_columns:
        execute(database_path, f"ALTER TABLE users ADD COLUMN email_verified {bool_type} NOT NULL DEFAULT {true_literal}")
    execute(
        database_path,
        """
        UPDATE users
        SET email = LOWER(username || '@boardsight.local')
        WHERE email IS NULL OR TRIM(email) = ''
        """,
    )
    execute(
        database_path,
        f"""
        UPDATE users
        SET email_verified = {true_literal}
        WHERE email_verified IS NULL
        """,
    )
    execute(database_path, "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    session_columns = table_columns(database_path, "sessions")
    if "user_id" not in session_columns:
        execute(
            database_path,
            "ALTER TABLE sessions ADD COLUMN user_id " + ("BIGINT DEFAULT 0" if is_postgres(database_path) else "INTEGER DEFAULT 0"),
        )
    if "expires_at" not in session_columns:
        execute(database_path, f"ALTER TABLE sessions ADD COLUMN expires_at {timestamp_type}")
    if "revoked_at" not in session_columns:
        execute(database_path, f"ALTER TABLE sessions ADD COLUMN revoked_at {timestamp_type}")


def legacy_hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def _is_argon2_hash(password_hash: str) -> bool:
    return str(password_hash or "").startswith("$argon2")


def _verify_password(password: str, password_hash: str) -> tuple[bool, bool]:
    stored_hash = str(password_hash or "")
    if not stored_hash:
        return False, False
    if _is_argon2_hash(stored_hash):
        try:
            PASSWORD_HASHER.verify(stored_hash, password)
            return True, PASSWORD_HASHER.check_needs_rehash(stored_hash)
        except (VerifyMismatchError, InvalidHashError):
            return False, False
    return secrets.compare_digest(legacy_hash_password(password), stored_hash), True


def _build_user_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": int(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "email_verified": bool(row.get("email_verified")),
    }


def get_user_by_identifier(database_path: Path, identifier: str) -> dict[str, Any] | None:
    init_auth_storage(database_path)
    resolved_identifier = identifier.strip().lower()
    row = fetchone(
        database_path,
        """
        SELECT id, username, email, display_name, role, password_hash, email_verified
        FROM users
        WHERE LOWER(username) = :identifier OR LOWER(email) = :identifier
        """,
        {"identifier": resolved_identifier},
    )
    return dict(row) if row is not None else None


def get_user_by_email(database_path: Path, email: str) -> dict[str, Any] | None:
    init_auth_storage(database_path)
    row = fetchone(
        database_path,
        """
        SELECT id, username, email, display_name, role, password_hash, email_verified
        FROM users
        WHERE LOWER(email) = LOWER(:email)
        """,
        {"email": email.strip().lower()},
    )
    return dict(row) if row is not None else None


def create_user(
    database_path: Path,
    username: str,
    password: str,
    role: str = "analyst",
    display_name: str | None = None,
    email: str | None = None,
    *,
    email_verified: bool = True,
) -> bool:
    init_auth_storage(database_path)
    resolved_display_name = (display_name or username).strip() or username
    resolved_email = (email or f"{username}@boardsight.local").strip().lower()
    existing = fetchone(
        database_path,
        """
        SELECT id
        FROM users
        WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)
        """,
        {"username": username, "email": resolved_email},
    )
    if existing is not None:
        return False

    insert_sql = """
        INSERT INTO users (username, email, display_name, password_hash, role, email_verified)
        VALUES (:username, :email, :display_name, :password_hash, :role, :email_verified)
    """
    if is_postgres(database_path):
        insert_sql += " ON CONFLICT DO NOTHING"
    else:
        insert_sql = insert_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
    execute(
        database_path,
        insert_sql,
        {
            "username": username,
            "email": resolved_email,
            "display_name": resolved_display_name,
            "password_hash": hash_password(password),
            "role": role,
            "email_verified": bool(email_verified),
        },
    )
    created = fetchone(database_path, "SELECT id FROM users WHERE LOWER(username) = LOWER(:username)", {"username": username})
    return created is not None


def upsert_admin_user(
    database_path: Path,
    *,
    username: str,
    password: str,
    email: str,
    display_name: str,
) -> dict[str, Any]:
    init_auth_storage(database_path)
    resolved_username = username.strip()
    resolved_email = email.strip().lower()
    resolved_display_name = display_name.strip() or resolved_username
    row = fetchone(
        database_path,
        """
        SELECT id, username, email
        FROM users
        WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)
        ORDER BY CASE WHEN LOWER(email) = LOWER(:email) THEN 0 ELSE 1 END
        LIMIT 1
        """,
        {"username": resolved_username, "email": resolved_email},
    )
    if row is None:
        create_user(
            database_path,
            resolved_username,
            password,
            "admin",
            display_name=resolved_display_name,
            email=resolved_email,
            email_verified=True,
        )
        created = get_user_by_username(database_path, resolved_username)
        if created is None:
            raise RuntimeError("Unable to create bootstrap admin user.")
        return created

    execute(
        database_path,
        """
        UPDATE users
        SET username = :username,
            email = :email,
            display_name = :display_name,
            password_hash = :password_hash,
            role = 'admin',
            email_verified = :email_verified
        WHERE id = :user_id
        """,
        {
            "username": resolved_username,
            "email": resolved_email,
            "display_name": resolved_display_name,
            "password_hash": hash_password(password),
            "email_verified": True,
            "user_id": int(row["id"]),
        },
    )
    updated = get_user_by_username(database_path, resolved_username)
    if updated is None:
        raise RuntimeError("Unable to update bootstrap admin user.")
    return updated


def _update_password_hash(database_path: Path, user_id: int, password: str) -> None:
    execute(
        database_path,
        "UPDATE users SET password_hash = :password_hash WHERE id = :user_id",
        {"password_hash": hash_password(password), "user_id": user_id},
    )


def authenticate_credentials(database_path: Path, identifier: str, password: str) -> tuple[dict[str, Any] | None, str]:
    init_auth_storage(database_path)
    row = get_user_by_identifier(database_path, identifier)
    if row is None:
        return None, "invalid_credentials"
    verified, should_rehash = _verify_password(password, str(row.get("password_hash") or ""))
    if not verified:
        return None, "invalid_credentials"
    user_id = int(row["id"])
    if should_rehash:
        _update_password_hash(database_path, user_id, password)
        row["password_hash"] = fetchone(database_path, "SELECT password_hash FROM users WHERE id = :user_id", {"user_id": user_id})["password_hash"]
    if not bool(row.get("email_verified")):
        return _build_user_payload(row), "email_not_verified"
    return _build_user_payload(row), "ok"


def _create_session(database_path: Path, user: dict[str, Any], ttl_seconds: int | None = None) -> dict[str, Any]:
    token = secrets.token_hex(24)
    expiry = _utcnow() + timedelta(seconds=ttl_seconds or session_ttl_seconds())
    execute(
        database_path,
        """
        INSERT INTO sessions (token, user_id, username, expires_at)
        VALUES (:token, :user_id, :username, :expires_at)
        """,
        {
            "token": token,
            "user_id": int(user["user_id"]),
            "username": user["username"],
            "expires_at": _format_timestamp(expiry),
        },
    )
    return {
        "token": token,
        "expires_at": _format_timestamp(expiry),
        **user,
    }


def authenticate_user(database_path: Path, identifier: str, password: str) -> dict[str, Any] | None:
    user, reason = authenticate_credentials(database_path, identifier, password)
    if reason != "ok" or user is None:
        return None
    return _create_session(database_path, user)


def get_session_user(database_path: Path, token: str) -> dict[str, Any] | None:
    init_auth_storage(database_path)
    row = fetchone(
        database_path,
        """
        SELECT u.id, u.username, u.email, u.display_name, u.role, u.email_verified,
               s.token, s.created_at, s.expires_at, s.revoked_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = :token
        """,
        {"token": token},
    )
    if row is None:
        return None
    if row.get("revoked_at"):
        return None
    expiry = _parse_timestamp(row.get("expires_at"))
    if expiry is None:
        created_at = _parse_timestamp(row.get("created_at")) or _utcnow()
        expiry = created_at + timedelta(seconds=session_ttl_seconds())
    if expiry <= _utcnow():
        revoke_session(database_path, token)
        return None
    return {
        **_build_user_payload(row),
        "token": row.get("token"),
        "expires_at": _format_timestamp(expiry),
    }


def revoke_session(database_path: Path, token: str) -> None:
    init_auth_storage(database_path)
    execute(
        database_path,
        """
        UPDATE sessions
        SET revoked_at = COALESCE(revoked_at, :revoked_at)
        WHERE token = :token
        """,
        {"token": token, "revoked_at": _format_timestamp(_utcnow())},
    )


def cleanup_expired_sessions(database_path: Path) -> int:
    init_auth_storage(database_path)
    expired_count_row = fetchone(
        database_path,
        """
        SELECT COUNT(*) AS count
        FROM sessions
        WHERE revoked_at IS NOT NULL
           OR (expires_at IS NOT NULL AND expires_at <= :now)
        """,
        {"now": _format_timestamp(_utcnow())},
    )
    execute(
        database_path,
        """
        DELETE FROM sessions
        WHERE revoked_at IS NOT NULL
           OR (expires_at IS NOT NULL AND expires_at <= :now)
        """,
        {"now": _format_timestamp(_utcnow())},
    )
    return int(expired_count_row.get("count") or 0) if expired_count_row else 0


def cleanup_expired_verification_tokens(database_path: Path) -> int:
    init_auth_storage(database_path)
    expired_count_row = fetchone(
        database_path,
        """
        SELECT COUNT(*) AS count
        FROM email_verification_tokens
        WHERE consumed_at IS NOT NULL
           OR expires_at <= :now
        """,
        {"now": _format_timestamp(_utcnow())},
    )
    execute(
        database_path,
        """
        DELETE FROM email_verification_tokens
        WHERE consumed_at IS NOT NULL
           OR expires_at <= :now
        """,
        {"now": _format_timestamp(_utcnow())},
    )
    return int(expired_count_row.get("count") or 0) if expired_count_row else 0


def mark_user_email_verified(database_path: Path, user_id: int) -> None:
    init_auth_storage(database_path)
    execute(
        database_path,
        "UPDATE users SET email_verified = :email_verified WHERE id = :user_id",
        {"email_verified": True, "user_id": user_id},
    )


def issue_email_verification_token(database_path: Path, user_id: int, email: str, ttl_seconds: int | None = None) -> str:
    init_auth_storage(database_path)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = _utcnow() + timedelta(seconds=ttl_seconds or verification_ttl_seconds())
    execute(
        database_path,
        """
        UPDATE email_verification_tokens
        SET consumed_at = COALESCE(consumed_at, :consumed_at)
        WHERE user_id = :user_id AND consumed_at IS NULL
        """,
        {"user_id": user_id, "consumed_at": _format_timestamp(_utcnow())},
    )
    execute(
        database_path,
        """
        INSERT INTO email_verification_tokens (user_id, email, token_hash, expires_at)
        VALUES (:user_id, :email, :token_hash, :expires_at)
        """,
        {
            "user_id": user_id,
            "email": email.strip().lower(),
            "token_hash": token_hash,
            "expires_at": _format_timestamp(expires_at),
        },
    )
    return raw_token


def verify_email_token(database_path: Path, token: str) -> dict[str, Any] | None:
    init_auth_storage(database_path)
    token_hash = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    row = fetchone(
        database_path,
        """
        SELECT id, user_id, email, expires_at, consumed_at
        FROM email_verification_tokens
        WHERE token_hash = :token_hash
        """,
        {"token_hash": token_hash},
    )
    if row is None:
        return None
    if row.get("consumed_at"):
        return None
    expiry = _parse_timestamp(row.get("expires_at"))
    if expiry is None or expiry <= _utcnow():
        return None
    execute(
        database_path,
        """
        UPDATE email_verification_tokens
        SET consumed_at = :consumed_at
        WHERE id = :token_id
        """,
        {"consumed_at": _format_timestamp(_utcnow()), "token_id": int(row["id"])},
    )
    mark_user_email_verified(database_path, int(row["user_id"]))
    return {
        "user_id": int(row["user_id"]),
        "email": row["email"],
    }


def get_user_by_username(database_path: Path, username: str) -> dict[str, Any] | None:
    init_auth_storage(database_path)
    row = fetchone(
        database_path,
        """
        SELECT id, username, email, display_name, role, email_verified
        FROM users
        WHERE LOWER(username) = LOWER(:username)
        """,
        {"username": username},
    )
    if row is None:
        return None
    return _build_user_payload(row)
