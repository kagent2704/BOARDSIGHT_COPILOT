from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from boardsight_ai import service
from boardsight_ai.auth import cleanup_expired_login_attempts, clear_login_attempts, reserve_login_attempt
from boardsight_ai.config import AppConfig
from boardsight_ai.providers import llm
from boardsight_ai.workspaces import _configured_sponsored_emails


def test_upload_streams_in_chunks_without_changing_bytes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(service, "MAX_UPLOAD_BYTES", 12)
    monkeypatch.setattr(service, "UPLOAD_CHUNK_BYTES", 4)
    destination = tmp_path / "meeting.mp4"
    upload = UploadFile(filename="meeting.mp4", file=BytesIO(b"hello-world"))

    total = asyncio.run(service._stream_upload_to_path(upload, destination))

    assert total == 11
    assert destination.read_bytes() == b"hello-world"


def test_upload_rejects_oversized_content_while_streaming(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(service, "MAX_UPLOAD_BYTES", 5)
    monkeypatch.setattr(service, "UPLOAD_CHUNK_BYTES", 3)
    destination = tmp_path / "meeting.mp4"
    upload = UploadFile(filename="meeting.mp4", file=BytesIO(b"123456"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service._stream_upload_to_path(upload, destination))

    assert exc_info.value.status_code == 413


def test_upload_extension_allowlist() -> None:
    assert service._validate_upload_name("meeting.MP4") == ".mp4"
    with pytest.raises(HTTPException) as exc_info:
        service._validate_upload_name("meeting.html")
    assert exc_info.value.status_code == 415


def test_sponsored_accounts_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("BOARDSIGHT_SPONSORED_EMAILS", " Founder@Example.com, second@example.com ")
    assert _configured_sponsored_emails() == {"founder@example.com", "second@example.com"}


def test_login_rate_limit_blocks_after_configured_failures(tmp_path: Path) -> None:
    db_path = tmp_path / "shared-rate-limit.db"
    key = "test-login-key"
    assert reserve_login_attempt(db_path, key, max_attempts=2, window_seconds=60, now_epoch=1000) == 0
    assert reserve_login_attempt(db_path, key, max_attempts=2, window_seconds=60, now_epoch=1001) == 0
    assert reserve_login_attempt(db_path, key, max_attempts=2, window_seconds=60, now_epoch=1002) == 58

    clear_login_attempts(db_path, key)
    assert reserve_login_attempt(db_path, key, max_attempts=2, window_seconds=60, now_epoch=1003) == 0


def test_login_rate_limit_window_expires_and_cleanup_removes_stale_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "shared-rate-limit.db"
    key = "expiring-login-key"
    assert reserve_login_attempt(db_path, key, max_attempts=1, window_seconds=60, now_epoch=2000) == 0
    assert reserve_login_attempt(db_path, key, max_attempts=1, window_seconds=60, now_epoch=2001) == 59
    assert reserve_login_attempt(db_path, key, max_attempts=1, window_seconds=60, now_epoch=2061) == 0
    assert cleanup_expired_login_attempts(db_path, window_seconds=60, now_epoch=2121) == 1


def test_gemini_api_key_is_sent_in_header_not_url(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": "grounded"}]}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {key.casefold(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    config = AppConfig(project_root=tmp_path, output_root=tmp_path, gemini_api_key="secret-test-key")

    response = llm._gemini_generate_text("meeting evidence", config)

    assert response is not None and response[0] == "grounded"
    assert "secret-test-key" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "secret-test-key"


def test_frontend_escapes_meeting_derived_trace_fields() -> None:
    app_js = (Path(__file__).resolve().parents[2] / "java-app" / "src" / "main" / "resources" / "public" / "app.js").read_text(encoding="utf-8")
    assert "<strong>${trace.title}</strong>" not in app_js
    assert '${escapeHtml(trace.title || "Decision trace")}' in app_js
    assert "<span>${speaker.speaker}</span>" not in app_js
