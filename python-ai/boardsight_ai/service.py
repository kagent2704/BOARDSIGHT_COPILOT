from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import threading
import uuid
from dataclasses import fields, is_dataclass
from datetime import datetime
from urllib.parse import unquote
from pathlib import Path
from typing import Any
from typing import get_type_hints
from typing import get_args, get_origin

CURRENT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = CURRENT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

try:
    from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
    from fastapi.responses import FileResponse
    import uvicorn
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "FastAPI service dependencies are missing. Install python-ai/requirements-core.txt first."
    ) from exc

from boardsight_ai.pipeline import run_pipeline, write_result
from boardsight_ai.providers.media import clip_video_fast
from boardsight_ai.agent_storage import (
    create_agent_execution_run,
    get_agent_execution_run,
    init_agent_storage,
    update_agent_execution_run,
)
from boardsight_ai.auth import authenticate_user, create_user, get_session_user, get_user_by_username, init_auth_storage
from boardsight_ai.config import default_config, resolve_runtime_config
from boardsight_ai.database import execute, fetchone
from boardsight_ai.gitlab_execution import build_gitlab_execution_plan, sync_plan_to_gitlab
from boardsight_ai.gitlab_storage import init_gitlab_storage, save_gitlab_sync
from boardsight_ai.live_meeting import (
    analyze_live_segments,
    analyze_live_chunk_media,
    append_transcript_dicts,
    transcript_dicts_to_segments,
    transcribe_live_chunk,
    write_live_result,
)
from boardsight_ai.live_storage import create_live_session, get_live_session, init_live_storage, parse_live_session_record, update_live_session
from boardsight_ai.features import decision_moments, visual_artifacts, workflow_engine
from boardsight_ai.features.scoring import _classifier as _scoring_classifier
from boardsight_ai.models import PipelineResult
from boardsight_ai.providers.llm import _summarizer, generate_text
from boardsight_ai.providers.speech import _faster_whisper_model
from boardsight_ai.storage import get_meeting_result, init_storage, list_meeting_results, save_meeting_result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "output" / "appdata"
AUTH_DB_PATH = DATA_DIR / "boardsight_auth.db"
MEETING_DB_PATH = DATA_DIR / "boardsight_meetings.db"
LIVE_DB_PATH = DATA_DIR / "boardsight_live.db"
GITLAB_DB_PATH = DATA_DIR / "boardsight_gitlab.db"
AGENT_DB_PATH = DATA_DIR / "boardsight_agent.db"
init_auth_storage(AUTH_DB_PATH)
init_storage(MEETING_DB_PATH)
init_live_storage(LIVE_DB_PATH)
init_gitlab_storage(GITLAB_DB_PATH)
init_agent_storage(AGENT_DB_PATH)
create_user(
    AUTH_DB_PATH,
    "admin",
    "boardsight123",
    "admin",
    display_name="BoardSight Admin",
    email="admin@boardsight.local",
)


def _assign_orphaned_runs_to_admin() -> None:
    admin_row = fetchone(
        AUTH_DB_PATH,
        "SELECT id, username FROM users WHERE username = :username",
        {"username": "admin"},
    )
    if admin_row is None:
        return

    execute(
        MEETING_DB_PATH,
        """
        UPDATE meetings
        SET user_id = :user_id, username = COALESCE(username, :username)
        WHERE user_id IS NULL
        """,
        {"user_id": int(admin_row["id"]), "username": str(admin_row["username"])},
    )


_assign_orphaned_runs_to_admin()

app = FastAPI(title="BoardSight AI Service", version="0.1.0")
WARM_MODELS_ON_STARTUP = os.getenv("BOARDSIGHT_WARM_MODELS", "0").strip().lower() in {"1", "true", "yes", "on"}
WARMUP_STATE: dict[str, object] = {
    "enabled": WARM_MODELS_ON_STARTUP,
    "completed": False,
    "in_progress": False,
    "steps": [],
}


def _warm_model_caches() -> None:
    WARMUP_STATE["in_progress"] = True
    config = default_config()
    steps: list[dict[str, str]] = []

    def record_step(name: str, loaded: bool) -> None:
        steps.append({"name": name, "status": "loaded" if loaded else "unavailable"})

    whisper_model = _faster_whisper_model(config.faster_whisper_model)
    record_step(f"faster-whisper:{config.faster_whisper_model}", whisper_model is not None)

    text_classifier = decision_moments._classifier(config.text_classifier_model)
    record_step(f"text-classifier:{config.text_classifier_model}", text_classifier is not None)
    record_step(f"workflow-classifier:{config.text_classifier_model}", workflow_engine._classifier(config.text_classifier_model) is not None)
    record_step(f"scoring-classifier:{config.text_classifier_model}", _scoring_classifier(config.text_classifier_model) is not None)

    image_classifier = visual_artifacts._image_classifier(config.image_classifier_model)
    record_step(f"image-classifier:{config.image_classifier_model}", image_classifier is not None)
    record_step("ocr:trocr-small-printed", visual_artifacts._ocr_components() is not None)
    record_step("image-captioning:blip-base", visual_artifacts._image_captioner() is not None)
    record_step("presentation-summary:flan-t5-small", _summarizer() is not None)

    WARMUP_STATE["completed"] = True
    WARMUP_STATE["in_progress"] = False
    WARMUP_STATE["steps"] = steps


@app.on_event("startup")
def warm_models_on_startup() -> None:
    if not WARM_MODELS_ON_STARTUP:
        return

    def _run_background_warmup() -> None:
        try:
            _warm_model_caches()
        except Exception as exc:
            WARMUP_STATE["completed"] = False
            WARMUP_STATE["in_progress"] = False
            WARMUP_STATE["error"] = str(exc)

    threading.Thread(target=_run_background_warmup, name="boardsight-model-warmup", daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    payload = {"status": "ok"}
    if WARM_MODELS_ON_STARTUP:
        if WARMUP_STATE.get("completed"):
            payload["model_warmup"] = "complete"
        elif WARMUP_STATE.get("in_progress"):
            payload["model_warmup"] = "warming"
        else:
            payload["model_warmup"] = "pending"
    return payload


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "BoardSight AI Service",
        "status": "ok",
        "ui_hint": "This is the AI backend. Open the BoardSight web service URL for the full product UI.",
        "health_path": "/health",
        "capabilities_path": "/api/v1/agent/capabilities",
    }


async def _collect_request_payload(request: Request, payload: dict | None = None) -> dict:
    request_payload = dict(payload or {})
    if request_payload:
        return request_payload

    try:
        parsed_json = await request.json()
        if isinstance(parsed_json, dict):
            request_payload.update(parsed_json)
    except Exception:
        pass

    if not request_payload:
        try:
            raw_body = await request.body()
            if raw_body:
                parsed_raw = json.loads(raw_body.decode("utf-8"))
                if isinstance(parsed_raw, dict):
                    request_payload.update(parsed_raw)
        except Exception:
            pass

    if not request_payload:
        try:
            form = await request.form()
            request_payload.update({str(key): str(value) for key, value in form.items()})
        except Exception:
            pass

    if request.query_params:
        for key, value in request.query_params.items():
            request_payload.setdefault(str(key), str(value))

    return request_payload


@app.post("/api/v1/auth/login")
async def login(request: Request, payload: dict | None = None) -> dict:
    request_payload = await _collect_request_payload(request, payload)
    identifier = str(request_payload.get("identifier", "") or request_payload.get("username", "") or request_payload.get("email", ""))
    password = str(request_payload.get("password", ""))
    session = authenticate_user(AUTH_DB_PATH, identifier, password)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid username, email, or password.")
    return session


@app.post("/api/v1/auth/register")
async def register(request: Request, payload: dict | None = None) -> dict:
    request_payload = await _collect_request_payload(request, payload)
    username = str(request_payload.get("username", "")).strip()
    email = str(request_payload.get("email", "")).strip().lower()
    password = str(request_payload.get("password", "")).strip()
    confirm_password = str(request_payload.get("confirm_password", "")).strip()
    role = str(request_payload.get("role", "analyst")).strip() or "analyst"
    display_name = str(request_payload.get("display_name", username)).strip() or username
    if not username or not email or not password or not confirm_password:
        raise HTTPException(status_code=400, detail="Username, email, password, and confirmation are required.")
    if confirm_password != password:
        raise HTTPException(status_code=400, detail="Password confirmation does not match.")
    created = create_user(AUTH_DB_PATH, username, password, role, display_name=display_name, email=email)
    if not created:
        raise HTTPException(status_code=409, detail="An account with that username or email already exists.")
    return {"status": "created", "username": username, "email": email, "display_name": display_name, "role": role}


def _require_session_user(request: Request) -> dict:
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    user = get_session_user(AUTH_DB_PATH, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    return user


def _require_agent_or_session_user(request: Request) -> dict:
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if token:
        user = get_session_user(AUTH_DB_PATH, token)
        if user is not None:
            return user

    runtime_config = default_config()
    expected_api_key = str(runtime_config.agent_api_key or "").strip()
    provided_api_key = str(request.headers.get("X-BoardSight-Agent-Key", "") or "").strip()
    if expected_api_key and provided_api_key and secrets.compare_digest(provided_api_key, expected_api_key):
        agent_user = get_user_by_username(AUTH_DB_PATH, "admin")
        if agent_user is not None:
            return agent_user

    if token:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    raise HTTPException(status_code=401, detail="Missing authorization token or agent API key.")


def _summarize_meeting_row(row: dict) -> dict:
    meeting_id = int(row["id"])
    run_name = str(row.get("run_name") or f"meeting-{meeting_id}")
    sentiment = str(row.get("overall_sentiment") or "analysis ready").strip()
    return {
        "id": str(meeting_id),
        "meetingId": meeting_id,
        "title": run_name.replace("-", " ").replace("_", " ").strip().title() or f"Meeting {meeting_id}",
        "conclusion": f"Sentiment: {sentiment.capitalize()} | Attention {float(row.get('overall_attention') or 0):.1f}% | Impact {float(row.get('impact_score') or 0):.1f}",
        "decisions": int(row.get("decision_count") or 0),
        "createdAt": str(row.get("created_at") or datetime.utcnow().isoformat()),
        "speakerCount": int(row.get("speaker_count") or 0),
        "visualArtifactCount": int(row.get("visual_artifact_count") or 0),
        "overallAttention": float(row.get("overall_attention") or 0),
        "overallSentiment": row.get("overall_sentiment"),
        "impactScore": float(row.get("impact_score") or 0),
        "productivityScore": float(row.get("productivity_score") or 0),
        "executionReadiness": float(row.get("execution_readiness") or 0),
        "analysisProfile": row.get("analysis_profile") or "recorded-fast",
        "sourceMode": row.get("source_mode") or "recorded",
        "executionTaskCount": int(row.get("execution_task_count") or 0),
        "riskSignalCount": int(row.get("risk_signal_count") or 0),
    }


def _resolve_owned_meeting_record(meeting_id: int, user: dict) -> dict:
    record = get_meeting_result(MEETING_DB_PATH, meeting_id, user_id=int(user["user_id"]))
    if record is None:
        raise HTTPException(status_code=404, detail="Stored analysis not found.")
    return record


def _hydrate_pipeline_value(type_hint, value):
    origin = get_origin(type_hint)
    if value is None:
        return None
    if origin is list:
        item_type = get_args(type_hint)[0] if get_args(type_hint) else Any
        return [_hydrate_pipeline_value(item_type, item) for item in value]
    if origin is dict:
        return value
    if isinstance(type_hint, type) and is_dataclass(type_hint):
        field_types = get_type_hints(type_hint)
        kwargs = {}
        for field in fields(type_hint):
            kwargs[field.name] = _hydrate_pipeline_value(field_types.get(field.name, field.type), value.get(field.name))
        return type_hint(**kwargs)
    return value


def _pipeline_result_from_payload(payload: dict[str, Any]) -> PipelineResult:
    return _hydrate_pipeline_value(PipelineResult, payload)


def _ensure_report_file(record: dict, file_name: str) -> Path:
    stored_output_dir = str(record.get("output_dir") or "").strip()
    output_dir = Path(stored_output_dir).resolve() if stored_output_dir else _resolve_output_dir(f"meeting-{record['id']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = (output_dir / file_name).resolve()
    if not str(candidate).startswith(str(output_dir)):
        raise HTTPException(status_code=400, detail="Invalid report path.")
    if candidate.exists():
        return candidate

    payload = json.loads(str(record.get("result_json") or "{}"))
    if not payload:
        raise HTTPException(status_code=404, detail="Stored analysis details are missing, so this report cannot be regenerated.")

    regenerated_result = _pipeline_result_from_payload(payload)
    write_result(regenerated_result, output_dir / "boardsight_result.json")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Requested report file could not be regenerated.")
    return candidate


@app.get("/api/v1/me")
def me(request: Request) -> dict:
    return _require_session_user(request)


@app.get("/api/v1/meetings")
def meetings(request: Request) -> dict:
    user = _require_session_user(request)
    rows = list_meeting_results(MEETING_DB_PATH, user_id=int(user["user_id"]))
    return {"items": [_summarize_meeting_row(row) for row in rows]}


@app.get("/api/v1/meetings/{meeting_id}")
def meeting_detail(meeting_id: int, request: Request) -> dict:
    user = _require_session_user(request)
    record = _resolve_owned_meeting_record(meeting_id, user)
    payload = json.loads(str(record.get("result_json") or "{}"))
    payload["storage"] = {
        "meeting_id": int(record["id"]),
        "output_dir": str(record.get("output_dir") or ""),
        "result_file": str(record.get("result_file") or ""),
        "created_at": str(record.get("created_at") or ""),
        "username": str(record.get("username") or ""),
    }
    return payload


@app.get("/api/v1/meetings/{meeting_id}/reports/{file_name}")
def meeting_report(meeting_id: int, file_name: str, request: Request):
    user = _require_session_user(request)
    record = _resolve_owned_meeting_record(meeting_id, user)
    candidate = _ensure_report_file(record, file_name)
    return FileResponse(candidate, filename=candidate.name)


def _build_output_payload(result, output_dir: Path, user: dict | None = None) -> dict:
    result_path = write_result(result, output_dir / "boardsight_result.json")
    meeting_id = save_meeting_result(
        MEETING_DB_PATH,
        result,
        output_dir=output_dir,
        result_file=result_path,
        user_id=int(user["user_id"]) if user is not None else None,
        username=str(user["username"]) if user is not None else None,
    )
    payload = result.to_dict()
    payload["storage"] = {
        "meeting_id": meeting_id,
        "auth_db": str(AUTH_DB_PATH),
        "meeting_db": str(MEETING_DB_PATH),
        "output_dir": str(output_dir),
        "result_file": str(result_path),
    }
    return payload


def _resolve_output_dir(output_dir_name: str | None) -> Path:
    output_root = PROJECT_ROOT / "output"
    run_name = (output_dir_name or f"service-run-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}").strip()
    safe_run_name = "".join(char if char.isalnum() or char in "-_." else "_" for char in run_name) or "service-run"
    output_dir = output_root / safe_run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _parse_optional_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _resolve_analysis_input(
    source_video_path: Path,
    output_dir: Path,
    start_seconds: float | None,
    end_seconds: float | None,
) -> tuple[Path, dict | None]:
    if start_seconds is None and end_seconds is None:
        return source_video_path, None
    clipped_path = output_dir / "analysis_input.mp4"
    analysis_range = clip_video_fast(source_video_path, clipped_path, start_seconds, end_seconds)
    return Path(str(analysis_range["output_path"])).resolve(), analysis_range


def _resolve_analysis_profile(value: str | None) -> str:
    profile = (value or "").strip().lower()
    return profile or "recorded-fast"


def _resolve_source_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    return mode or "recorded"


def _resolve_live_output_dir(session_id: str) -> Path:
    output_dir = PROJECT_ROOT / "output" / f"live-session-{session_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _owned_live_session(session_id: str, user: dict) -> dict:
    record = get_live_session(LIVE_DB_PATH, session_id, user_id=int(user["user_id"]))
    if record is None:
        raise HTTPException(status_code=404, detail="Live session not found.")
    return parse_live_session_record(record)


def _build_live_response(record: dict, state: dict | None = None) -> dict:
    payload = dict(state or record.get("state") or {})
    payload.setdefault("session_id", record["session_id"])
    payload.setdefault("title", record.get("title") or "Live Meeting")
    payload.setdefault("status", record.get("status") or "active")
    payload.setdefault("source_type", record.get("source_type") or "display-audio")
    payload.setdefault("analysis_profile", record.get("analysis_profile") or "live")
    payload["storage"] = {
        "session_id": record["session_id"],
        "output_dir": str(record.get("output_dir") or ""),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
    }
    if record.get("final_result") and payload.get("status") == "finalized":
        payload["final_result"] = record["final_result"]
    return payload


def _process_live_chunk_path(
    *,
    record: dict,
    session_id: str,
    chunk_path: Path,
    chunk_start_seconds: float | None,
    chunk_end_seconds: float | None,
) -> dict:
    output_dir = Path(str(record["output_dir"]))
    runtime_config = resolve_runtime_config(
        default_config(output_root=output_dir),
        analysis_profile=str(record.get("analysis_profile") or "live"),
        source_mode="live",
    )
    start_offset = float(chunk_start_seconds or 0.0)
    new_segments = transcribe_live_chunk(
        chunk_path,
        runtime_config,
        start_offset_seconds=start_offset,
        speaker_name="Live Speaker",
    )
    transcript = append_transcript_dicts(list(record["transcript"]), new_segments)
    segments = transcript_dicts_to_segments(transcript)
    chunk_media_state = analyze_live_chunk_media(
        chunk_path,
        runtime_config,
        start_offset_seconds=start_offset,
        transcript_segments=new_segments,
    )
    previous_state = dict(record.get("state") or {})
    cumulative_visuals = [*(previous_state.get("visual_artifacts", []) or []), *(chunk_media_state.get("visual_artifacts", []) or [])]
    previous_attention = previous_state.get("attention_sentiment", {}) or {}
    merged_attention = previous_attention
    if chunk_media_state.get("attention_sentiment"):
        from boardsight_ai.live_meeting import _attention_from_dict, _attention_to_dict, _merge_attention
        merged_attention = _attention_to_dict(
            _merge_attention(
                _attention_from_dict(previous_attention),
                _attention_from_dict(chunk_media_state.get("attention_sentiment") or {}),
            )
        )
    cumulative_presentation = [*(previous_state.get("presentation_windows", []) or [])]
    if chunk_media_state.get("presentation_insights"):
        cumulative_presentation.append(chunk_media_state["presentation_insights"])
    state = analyze_live_segments(
        segments,
        runtime_config,
        session_id=session_id,
        title=str(record.get("title") or "Live Meeting"),
        source_type=str(record.get("source_type") or "display-audio"),
        status=str(record.get("status") or "active"),
        visual_artifact_payloads=cumulative_visuals,
        cumulative_attention=merged_attention,
        presentation_windows=cumulative_presentation,
    )
    state["last_chunk"] = {
        "start_seconds": start_offset,
        "end_seconds": float(chunk_end_seconds or start_offset),
        "segment_count": len(new_segments),
    }
    state["warnings"] = [*(state.get("warnings", []) or []), *(chunk_media_state.get("warnings", []) or [])]
    update_live_session(LIVE_DB_PATH, session_id, transcript=transcript, state=state)
    return state


def _recorded_meeting_to_execution_source(record: dict) -> tuple[dict[str, Any], str]:
    payload = json.loads(str(record.get("result_json") or "{}"))
    source = {
        "decisions": payload.get("decision_moments", []),
        "action_items": payload.get("workflow_model", {}).get("execution_plan", []),
        "problems": [],
        "discussion_points": [
            segment.get("text", "")
            for segment in (payload.get("transcript", {}).get("segments", []) or [])[:6]
            if segment.get("text")
        ],
    }
    title = str(record.get("run_name") or f"Meeting {record.get('id')}")
    return source, title


def _compact_transcript_points(transcript_segments: list[dict[str, Any]], limit: int = 8) -> list[str]:
    points: list[str] = []
    for segment in transcript_segments[:limit]:
        text = str(segment.get("text") or "").strip()
        if text:
            points.append(text)
    return points


def _recorded_meeting_agent_context(record: dict) -> dict[str, Any]:
    payload = json.loads(str(record.get("result_json") or "{}"))
    transcript_segments = list(payload.get("transcript", {}).get("segments", []) or [])
    contract = payload.get("metadata", {}).get("agentic_contract", {}) or {}
    decision_items = list(payload.get("decision_moments", []) or [])
    action_items = list(payload.get("workflow_model", {}).get("execution_plan", []) or [])
    return {
        "source_kind": "meeting",
        "source_id": str(record.get("id")),
        "title": str(record.get("run_name") or f"Meeting {record.get('id')}"),
        "status": "finalized",
        "source_mode": str(record.get("source_mode") or "recorded"),
        "analysis_profile": str(record.get("analysis_profile") or "recorded-fast"),
        "created_at": str(record.get("created_at") or ""),
        "summary": {
            "meeting_conclusion": payload.get("meeting_scores", {}).get("meeting_conclusion"),
            "impact_score": payload.get("meeting_scores", {}).get("impact_score"),
            "productivity_score": payload.get("meeting_scores", {}).get("productivity_score"),
            "execution_readiness": payload.get("meeting_scores", {}).get("execution_readiness"),
            "discussion_points": _compact_transcript_points(transcript_segments),
        },
        "counts": {
            "transcript_segments": len(transcript_segments),
            "decisions": len(decision_items),
            "action_items": len(action_items),
            "risks": len(contract.get("entities", {}).get("risk_signals", []) or []),
            "visual_artifacts": len(payload.get("visual_artifacts", []) or []),
        },
        "agentic_contract": contract,
        "decisions": decision_items,
        "action_items": action_items,
        "storage": {
            "meeting_id": int(record["id"]),
            "output_dir": str(record.get("output_dir") or ""),
            "result_file": str(record.get("result_file") or ""),
        },
    }


def _live_agent_context(record: dict) -> dict[str, Any]:
    state = dict(record.get("state") or {})
    transcript_segments = list(record.get("transcript") or [])
    contract = state.get("agentic_contract", {}) or {}
    discussion_points: list[str] = []
    for item in (state.get("discussion_points", []) or [])[:8]:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            discussion_points.append(text)
    return {
        "source_kind": "live",
        "source_id": str(record.get("session_id")),
        "title": str(record.get("title") or "Live Meeting"),
        "status": str(record.get("status") or "active"),
        "source_mode": "live",
        "analysis_profile": str(record.get("analysis_profile") or "live"),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
        "summary": {
            "rolling_summary": state.get("rolling_summary"),
            "final_summary": state.get("final_summary"),
            "meeting_outcomes": list(state.get("meeting_outcomes", []) or []),
            "discussion_points": discussion_points,
        },
        "counts": {
            "transcript_segments": len(transcript_segments),
            "decisions": len(state.get("decisions", []) or []),
            "action_items": len(state.get("action_items", []) or []),
            "problems": len(state.get("problems", []) or []),
            "visual_artifacts": len(state.get("visual_artifacts", []) or []),
        },
        "agentic_contract": contract,
        "storage": {
            "session_id": str(record.get("session_id") or ""),
            "output_dir": str(record.get("output_dir") or ""),
        },
    }


def _resolve_agent_source_context(source_kind: str, source_id: str, user: dict) -> dict[str, Any]:
    normalized_kind = str(source_kind or "").strip().lower()
    if normalized_kind == "live":
        record = _owned_live_session(source_id, user)
        return _live_agent_context(record)
    if normalized_kind == "meeting":
        record = _resolve_owned_meeting_record(int(source_id), user)
        return _recorded_meeting_agent_context(record)
    raise HTTPException(status_code=400, detail="source_kind must be 'live' or 'meeting'.")


def _resolve_agent_connection(request_payload: dict[str, Any]) -> dict[str, Any]:
    nested = request_payload.get("connection", {})
    if isinstance(nested, dict) and nested:
        return nested
    flat_connection = {
        "base_url": str(request_payload.get("gitlab_base_url", "") or "").strip(),
        "project_id": str(request_payload.get("gitlab_project_id", "") or "").strip(),
        "private_token": str(request_payload.get("gitlab_private_token", "") or "").strip(),
    }
    return {key: value for key, value in flat_connection.items() if value}


def _latest_source_context(user: dict[str, Any]) -> dict[str, Any]:
    try:
        meeting_rows = list_meeting_results(MEETING_DB_PATH, user_id=int(user["user_id"]))
        if meeting_rows:
            return _recorded_meeting_agent_context(meeting_rows[0])
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="No meeting context is available yet.")


def _resolve_chat_source_context(request_payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    source_kind = str(request_payload.get("source_kind", "") or "").strip().lower()
    source_id = str(request_payload.get("source_id", "") or "").strip()
    if source_kind and source_id:
        return _resolve_agent_source_context(source_kind, source_id, user)
    return _latest_source_context(user)


def _extract_chat_lists(context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    contract = context.get("agentic_contract", {}) or {}
    entities = contract.get("entities", {}) if isinstance(contract, dict) else {}
    decisions = list(entities.get("decisions", []) or context.get("decisions", []) or [])
    actions = list(entities.get("actions", []) or context.get("action_items", []) or [])
    risks = list(entities.get("risk_signals", []) or [])
    summary = context.get("summary", {}) if isinstance(context.get("summary"), dict) else {}
    discussion_points = [str(item).strip() for item in (summary.get("discussion_points", []) or []) if str(item).strip()]
    outcomes_raw = summary.get("meeting_outcomes", []) or []
    outcomes: list[str] = []
    for item in outcomes_raw:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("summary") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            outcomes.append(text)
    return decisions, actions, risks, discussion_points, outcomes


def _format_bulleted_items(items: list[str], prefix: str = "- ") -> str:
    if not items:
        return ""
    return "\n".join(f"{prefix}{item}" for item in items[:5])


def _answer_from_structure(question: str, context: dict[str, Any]) -> str:
    lowered = question.lower()
    decisions, actions, risks, discussion_points, outcomes = _extract_chat_lists(context)
    summary = context.get("summary", {}) if isinstance(context.get("summary"), dict) else {}
    title = str(context.get("title") or "this meeting")

    if any(keyword in lowered for keyword in ["decision", "decide", "agreed"]):
        if not decisions:
            return f"I did not find explicit structured decisions for {title} yet."
        decision_lines = []
        for item in decisions[:5]:
            text = str(item.get("text") or item.get("title") or "Decision identified").strip()
            owner = str(item.get("owner") or item.get("speaker") or "").strip()
            meta = f" ({owner})" if owner else ""
            decision_lines.append(f"{text}{meta}")
        return "Here are the main decisions I found:\n" + _format_bulleted_items(decision_lines)

    if any(keyword in lowered for keyword in ["action", "todo", "to-do", "task", "owner", "assignee"]):
        if not actions:
            return f"I did not find structured action items for {title} yet."
        action_lines = []
        for item in actions[:6]:
            label = str(item.get("title") or item.get("text") or item.get("task") or "Follow-up item").strip()
            owner = str(item.get("owner") or item.get("assignee") or item.get("speaker") or "Unassigned").strip()
            due = str(item.get("deadline") or item.get("due_date") or "").strip()
            suffix = f" | owner: {owner}" + (f" | due: {due}" if due else "")
            action_lines.append(f"{label}{suffix}")
        return "Here are the follow-up actions I found:\n" + _format_bulleted_items(action_lines)

    if any(keyword in lowered for keyword in ["blocker", "risk", "problem", "issue"]):
        if not risks:
            return f"I did not find structured blockers or risk signals for {title}."
        risk_lines = []
        for item in risks[:6]:
            label = str(item.get("description") or item.get("text") or "Risk identified").strip()
            category = str(item.get("kind") or item.get("category") or "risk").strip()
            owner = str(item.get("speaker") or item.get("owner") or "").strip()
            meta = " | ".join(part for part in [category, owner] if part)
            risk_lines.append(f"{label}" + (f" | {meta}" if meta else ""))
        return "These are the main blockers and risks I found:\n" + _format_bulleted_items(risk_lines)

    if any(
        keyword in lowered
        for keyword in [
            "outcome",
            "result",
            "summary",
            "summarize",
            "summarise",
            "about",
            "happened",
            "goal",
            "purpose",
            "objective",
            "agenda",
        ]
    ):
        summary_text = str(summary.get("final_summary") or summary.get("rolling_summary") or summary.get("meeting_conclusion") or "").strip()
        if any(keyword in lowered for keyword in ["goal", "purpose", "objective", "agenda"]):
            if discussion_points:
                return (
                    f"Based on the transcript, {title} appears to focus on:\n"
                    + _format_bulleted_items(discussion_points[:5])
                )
            if summary_text:
                return summary_text
        if outcomes:
            return summary_text + ("\n\nOutcomes:\n" if summary_text else "Meeting outcomes:\n") + _format_bulleted_items(outcomes)
        if discussion_points:
            return summary_text + ("\n\nDiscussion points:\n" if summary_text else "Discussion points:\n") + _format_bulleted_items(discussion_points)
        if summary_text:
            return summary_text

    return ""


def _grounded_chat_fallback(question: str, context: dict[str, Any]) -> str:
    decisions, actions, risks, discussion_points, outcomes = _extract_chat_lists(context)
    summary = context.get("summary", {}) if isinstance(context.get("summary"), dict) else {}
    title = str(context.get("title") or "this meeting")
    summary_text = str(
        summary.get("final_summary")
        or summary.get("rolling_summary")
        or summary.get("meeting_conclusion")
        or ""
    ).strip()
    lowered = question.lower()

    if any(keyword in lowered for keyword in ["goal", "purpose", "objective", "agenda"]):
        if discussion_points:
            return (
                f"I am staying grounded to the stored transcript for {title}. "
                "The meeting appears to focus on:\n"
                + _format_bulleted_items(discussion_points[:5])
            )
        if summary_text:
            return summary_text

    lines: list[str] = []
    if summary_text:
        lines.append(summary_text)
    if discussion_points:
        lines.append("Discussion points:\n" + _format_bulleted_items(discussion_points[:5]))
    if decisions:
        decision_lines = [str(item.get("text") or item.get("title") or "Decision identified").strip() for item in decisions[:3]]
        lines.append("Decisions:\n" + _format_bulleted_items(decision_lines))
    if actions:
        action_lines = [str(item.get("title") or item.get("text") or item.get("task") or "Follow-up item").strip() for item in actions[:3]]
        lines.append("Action items:\n" + _format_bulleted_items(action_lines))
    if risks:
        risk_lines = [str(item.get("description") or item.get("text") or "Risk identified").strip() for item in risks[:3]]
        lines.append("Risks:\n" + _format_bulleted_items(risk_lines))
    if outcomes:
        lines.append("Outcomes:\n" + _format_bulleted_items(outcomes[:3]))

    if lines:
        return "\n\n".join(lines)
    return (
        f"I do not have enough grounded meeting detail to answer that confidently for {title}. "
        "Try asking about the summary, decisions, action items, or discussion points."
    )


def _build_chat_prompt(question: str, context: dict[str, Any]) -> str:
    decisions, actions, risks, discussion_points, outcomes = _extract_chat_lists(context)
    summary = context.get("summary", {}) if isinstance(context.get("summary"), dict) else {}
    summary_line = str(
        summary.get("final_summary")
        or summary.get("rolling_summary")
        or summary.get("meeting_conclusion")
        or "Summary unavailable."
    ).strip()

    def compact(items: list[str]) -> str:
        return "; ".join(items[:4]) if items else "None"

    decision_text = compact([str(item.get("text") or item.get("title") or "").strip() for item in decisions if str(item.get("text") or item.get("title") or "").strip()])
    action_text = compact([str(item.get("title") or item.get("text") or item.get("task") or "").strip() for item in actions if str(item.get("title") or item.get("text") or item.get("task") or "").strip()])
    risk_text = compact([str(item.get("description") or item.get("text") or "").strip() for item in risks if str(item.get("description") or item.get("text") or "").strip()])
    discussion_text = compact(discussion_points)
    outcome_text = compact(outcomes)

    return (
        "You are BoardSight Copilot. Answer the user's question using only the provided meeting context. "
        "Be concise, practical, and specific. If context is missing, say so plainly and suggest the next useful question.\n\n"
        f"Meeting title: {context.get('title')}\n"
        f"Source kind: {context.get('source_kind')}\n"
        f"Status: {context.get('status')}\n"
        f"Summary: {summary_line}\n"
        f"Discussion points: {discussion_text}\n"
        f"Decisions: {decision_text}\n"
        f"Action items: {action_text}\n"
        f"Risks and blockers: {risk_text}\n"
        f"Outcomes: {outcome_text}\n\n"
        f"User question: {question}"
    )


def _run_pipeline_for_shared_path(
    shared_file_path: str,
    output_dir_name: str | None,
    user: dict | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    analysis_profile: str | None = None,
    source_mode: str | None = None,
) -> dict:
    candidate_path = Path(unquote(shared_file_path)).resolve()
    output_root = PROJECT_ROOT / "output"
    if not str(candidate_path).startswith(str(output_root.resolve())):
        raise HTTPException(status_code=400, detail="Shared file path must be inside the output directory.")
    if not candidate_path.exists():
        raise HTTPException(status_code=400, detail="Shared file path does not exist for AI processing.")
    output_dir = _resolve_output_dir(output_dir_name)
    analysis_input_path, analysis_range = _resolve_analysis_input(candidate_path, output_dir, start_seconds, end_seconds)
    runtime_config = resolve_runtime_config(
        default_config(output_root=output_dir),
        analysis_profile=_resolve_analysis_profile(analysis_profile),
        source_mode=_resolve_source_mode(source_mode),
    )
    result = run_pipeline(
        analysis_input_path,
        output_dir,
        config=runtime_config,
        analysis_range=analysis_range,
        analysis_profile=runtime_config.default_analysis_profile,
        source_mode=_resolve_source_mode(source_mode),
    )
    return _build_output_payload(result, output_dir, user=user)


@app.post("/api/v1/pipeline/run-path")
async def run_pipeline_path_endpoint(request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    request_payload = payload or {}
    if not request_payload:
        try:
            request_payload = await request.json()
        except Exception:
            request_payload = {}

    file_path = str(request_payload.get("file_path", "")).strip() or str(request.query_params.get("file_path", "")).strip()
    output_dir_name = (
        str(request_payload.get("output_dir_name", "")).strip()
        or str(request.query_params.get("output_dir_name", "")).strip()
        or None
    )
    start_seconds = _parse_optional_float(request_payload.get("start_seconds", request.query_params.get("start_seconds")))
    end_seconds = _parse_optional_float(request_payload.get("end_seconds", request.query_params.get("end_seconds")))
    analysis_profile = str(request_payload.get("analysis_profile", request.query_params.get("analysis_profile", ""))).strip() or None
    source_mode = str(request_payload.get("source_mode", request.query_params.get("source_mode", ""))).strip() or None
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required.")
    return _run_pipeline_for_shared_path(
        file_path,
        output_dir_name,
        user=user,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        analysis_profile=analysis_profile,
        source_mode=source_mode,
    )


@app.post("/api/v1/pipeline/run")
async def run_pipeline_endpoint(
    request: Request,
    file: UploadFile | None = File(default=None),
    upload: UploadFile | None = File(default=None),
    meeting_file: UploadFile | None = File(default=None),
    output_dir_name: str | None = Form(default=None),
) -> dict:
    user = _require_session_user(request)
    resolved_upload = file or upload or meeting_file
    request_query = request.query_params
    request_payload: dict = {}

    if output_dir_name is None:
        output_dir_name = request_query.get("output_dir_name")

    request_content_type = request.headers.get("content-type", "")
    if "application/json" in request_content_type.lower():
        try:
            request_payload = await request.json()
        except Exception:
            request_payload = {}
        if output_dir_name is None:
            output_dir_name = str(request_payload.get("output_dir_name", "")).strip() or None

    if resolved_upload is None:
        try:
            form = await request.form()
        except Exception:
            form = None
        if form is not None:
            for field_name in ("file", "upload", "meeting_file"):
                candidate = form.get(field_name)
                if candidate is not None and hasattr(candidate, "filename") and hasattr(candidate, "read"):
                    resolved_upload = candidate
                    break

    raw_upload_bytes = b""
    raw_upload_name = request.headers.get("X-Filename") or request_query.get("filename") or "meeting.mp4"
    shared_file_path = str(request_payload.get("file_path", "")).strip() or request_query.get("file_path")
    start_seconds = _parse_optional_float(request_payload.get("start_seconds", request_query.get("start_seconds")))
    end_seconds = _parse_optional_float(request_payload.get("end_seconds", request_query.get("end_seconds")))
    analysis_profile = str(request_payload.get("analysis_profile", request_query.get("analysis_profile", ""))).strip() or "recorded-fast"
    source_mode = str(request_payload.get("source_mode", request_query.get("source_mode", ""))).strip() or "recorded"
    if resolved_upload is None:
        if shared_file_path:
            return _run_pipeline_for_shared_path(
                shared_file_path,
                output_dir_name,
                user=user,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                analysis_profile=analysis_profile,
                source_mode=source_mode,
            )

        try:
            raw_upload_bytes = await request.body()
        except Exception:
            raw_upload_bytes = b""
        if not raw_upload_bytes:
            raise HTTPException(status_code=400, detail="No uploaded file was provided to the AI service.")

    resolved_name = resolved_upload.filename if resolved_upload is not None else unquote(raw_upload_name)
    suffix = Path(resolved_name or "meeting.mp4").suffix or ".mp4"
    output_dir = _resolve_output_dir(output_dir_name)

    with tempfile.TemporaryDirectory(prefix="boardsight-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        video_path = temp_dir / f"upload{suffix}"
        if resolved_upload is not None:
            video_path.write_bytes(await resolved_upload.read())
        else:
            video_path.write_bytes(raw_upload_bytes)

        if not video_path.exists():
            raise HTTPException(status_code=400, detail="Failed to persist uploaded file.")

        analysis_input_path, analysis_range = _resolve_analysis_input(video_path, output_dir, start_seconds, end_seconds)
        runtime_config = resolve_runtime_config(
            default_config(output_root=output_dir),
            analysis_profile=_resolve_analysis_profile(analysis_profile),
            source_mode=_resolve_source_mode(source_mode),
        )
        result = run_pipeline(
            analysis_input_path,
            output_dir,
            config=runtime_config,
            analysis_range=analysis_range,
            analysis_profile=runtime_config.default_analysis_profile,
            source_mode=_resolve_source_mode(source_mode),
        )
        return _build_output_payload(result, output_dir, user=user)


@app.post("/api/v1/live/start")
async def start_live_session(request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    title = str(request_payload.get("title", "")).strip() or f"Live Meeting {datetime.utcnow().strftime('%H:%M:%S')}"
    source_type = str(request_payload.get("source_type", "display-audio")).strip() or "display-audio"
    analysis_profile = _resolve_analysis_profile(str(request_payload.get("analysis_profile", "live")).strip() or "live")
    session_id = uuid.uuid4().hex[:12]
    output_dir = _resolve_live_output_dir(session_id)
    create_live_session(
        LIVE_DB_PATH,
        session_id=session_id,
        user_id=int(user["user_id"]),
        username=str(user["username"]),
        title=title,
        source_type=source_type,
        analysis_profile=analysis_profile,
        output_dir=output_dir,
    )
    initial_state = {
        "session_id": session_id,
        "title": title,
        "status": "active",
        "source_type": source_type,
        "analysis_profile": analysis_profile,
        "transcript": [],
        "rolling_summary": "Live meeting started. Waiting for transcript chunks.",
        "discussion_points": [],
        "problems": [],
        "decisions": [],
        "action_items": [],
        "prioritized_decisions": [],
        "decision_traces": [],
        "actionable_insights": [],
        "suggestions": [
            "Share the meeting tab with audio for the strongest live capture.",
            "Keep the session running until formal decisions and next steps are spoken clearly.",
        ],
        "meeting_outcomes": [],
        "meeting_scores": {},
        "warnings": [],
        "agentic_contract": {
            "source_mode": "live",
            "analysis_profile": analysis_profile,
        },
    }
    update_live_session(LIVE_DB_PATH, session_id, transcript=[], state=initial_state)
    record = _owned_live_session(session_id, user)
    return _build_live_response(record, initial_state)


@app.get("/api/v1/live/{session_id}")
def get_live_session_endpoint(session_id: str, request: Request) -> dict:
    user = _require_session_user(request)
    record = _owned_live_session(session_id, user)
    return _build_live_response(record)


@app.post("/api/v1/live/{session_id}/append-text")
async def append_live_text(session_id: str, request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    record = _owned_live_session(session_id, user)
    request_payload = await _collect_request_payload(request, payload)
    text = str(request_payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Live text chunk is required.")
    start_seconds = float(request_payload.get("start_seconds", 0.0) or 0.0)
    end_seconds = float(request_payload.get("end_seconds", start_seconds + 4.0) or (start_seconds + 4.0))
    speaker = str(request_payload.get("speaker", "Live Speaker")).strip() or "Live Speaker"
    transcript = list(record["transcript"])
    transcript.append(
        {
            "start": start_seconds,
            "end": end_seconds,
            "speaker": speaker,
            "text": text,
            "confidence": 0.7,
        }
    )
    segments = transcript_dicts_to_segments(transcript)
    runtime_config = resolve_runtime_config(
        default_config(output_root=Path(str(record["output_dir"]))),
        analysis_profile=str(record.get("analysis_profile") or "live"),
        source_mode="live",
    )
    state = analyze_live_segments(
        segments,
        runtime_config,
        session_id=session_id,
        title=str(record.get("title") or "Live Meeting"),
        source_type=str(record.get("source_type") or "manual"),
        status=str(record.get("status") or "active"),
        visual_artifact_payloads=list((record.get("state") or {}).get("visual_artifacts", []) or []),
        cumulative_attention=((record.get("state") or {}).get("attention_sentiment", {}) or {}),
        presentation_windows=list((record.get("state") or {}).get("presentation_windows", []) or []),
    )
    update_live_session(LIVE_DB_PATH, session_id, transcript=transcript, state=state)
    refreshed = _owned_live_session(session_id, user)
    return _build_live_response(refreshed, state)


@app.post("/api/v1/live/{session_id}/chunk")
async def append_live_chunk(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    chunk_start_seconds: float | None = Form(default=None),
    chunk_end_seconds: float | None = Form(default=None),
) -> dict:
    user = _require_session_user(request)
    record = _owned_live_session(session_id, user)
    output_dir = Path(str(record["output_dir"]))
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "chunk.webm").suffix or ".webm"
    chunk_index = len(record["transcript"])
    chunk_path = chunks_dir / f"chunk-{chunk_index:05d}{suffix}"
    chunk_path.write_bytes(await file.read())
    state = _process_live_chunk_path(
        record=record,
        session_id=session_id,
        chunk_path=chunk_path,
        chunk_start_seconds=chunk_start_seconds,
        chunk_end_seconds=chunk_end_seconds,
    )
    refreshed = _owned_live_session(session_id, user)
    return _build_live_response(refreshed, state)


@app.post("/api/v1/live/{session_id}/chunk-path")
@app.get("/api/v1/live/{session_id}/chunk-path")
async def append_live_chunk_path(session_id: str, request: Request) -> dict:
    user = _require_session_user(request)
    record = _owned_live_session(session_id, user)
    raw_body = await request.body()
    payload: dict[str, Any] = {}
    if raw_body.strip():
        payload = json.loads(raw_body)
    if not payload:
        payload = dict(request.query_params)

    shared_file_path = str(payload.get("shared_file_path") or "").strip()
    if not shared_file_path:
        raise HTTPException(status_code=400, detail="Missing shared file path.")
    chunk_path = Path(unquote(shared_file_path)).resolve()
    output_root = PROJECT_ROOT / "output"
    if not str(chunk_path).startswith(str(output_root.resolve())):
        raise HTTPException(status_code=400, detail="Shared live chunk must be inside the output directory.")
    if not chunk_path.exists():
        raise HTTPException(status_code=400, detail="Shared live chunk path does not exist.")

    state = _process_live_chunk_path(
        record=record,
        session_id=session_id,
        chunk_path=chunk_path,
        chunk_start_seconds=_parse_optional_float(payload.get("chunk_start_seconds")),
        chunk_end_seconds=_parse_optional_float(payload.get("chunk_end_seconds")),
    )
    try:
        chunk_path.unlink(missing_ok=True)
    except Exception:
        pass
    refreshed = _owned_live_session(session_id, user)
    return _build_live_response(refreshed, state)


@app.post("/api/v1/live/{session_id}/finalize")
def finalize_live_session(session_id: str, request: Request) -> dict:
    user = _require_session_user(request)
    record = _owned_live_session(session_id, user)
    segments = transcript_dicts_to_segments(list(record["transcript"]))
    runtime_config = resolve_runtime_config(
        default_config(output_root=Path(str(record["output_dir"]))),
        analysis_profile=str(record.get("analysis_profile") or "live"),
        source_mode="live",
    )
    final_state = analyze_live_segments(
        segments,
        runtime_config,
        session_id=session_id,
        title=str(record.get("title") or "Live Meeting"),
        source_type=str(record.get("source_type") or "display-audio"),
        status="finalized",
        visual_artifact_payloads=list((record.get("state") or {}).get("visual_artifacts", []) or []),
        cumulative_attention=((record.get("state") or {}).get("attention_sentiment", {}) or {}),
        presentation_windows=list((record.get("state") or {}).get("presentation_windows", []) or []),
    )
    final_state["final_summary"] = final_state.get("rolling_summary", "")
    final_result_path = write_live_result(final_state, Path(str(record["output_dir"])))
    final_state["storage"] = {
        "session_id": session_id,
        "output_dir": str(record.get("output_dir") or ""),
        "result_file": str(final_result_path),
    }
    update_live_session(
        LIVE_DB_PATH,
        session_id,
        transcript=list(record["transcript"]),
        state=final_state,
        status="finalized",
        final_result=final_state,
    )
    refreshed = _owned_live_session(session_id, user)
    return _build_live_response(refreshed, final_state)


@app.get("/api/v1/agent/capabilities")
def agent_capabilities(request: Request) -> dict:
    _require_agent_or_session_user(request)
    return {
        "agent_runtime": "google-cloud-agent-builder-target",
        "boardSight_role": "meeting-perception-and-execution-memory",
        "supported_sources": ["meeting", "live"],
        "execution_targets": ["gitlab-mcp"],
        "recommended_tools": [
            {
                "name": "list_sources",
                "method": "GET",
                "path": "/api/v1/agent/sources",
                "purpose": "Discover live and recorded meeting sources available to the agent.",
            },
            {
                "name": "get_source_context",
                "method": "GET",
                "path": "/api/v1/agent/context/{source_kind}/{source_id}",
                "purpose": "Fetch normalized meeting memory and the agentic contract.",
            },
            {
                "name": "preview_execution",
                "method": "POST",
                "path": "/api/v1/agent/execution/preview",
                "purpose": "Generate an approval-gated GitLab execution plan.",
            },
            {
                "name": "approve_execution",
                "method": "POST",
                "path": "/api/v1/agent/execution/approve",
                "purpose": "Execute an approved GitLab sync after user approval.",
            },
            {
                "name": "get_execution_status",
                "method": "GET",
                "path": "/api/v1/agent/execution/{approval_id}",
                "purpose": "Inspect the approval and downstream sync status.",
            },
        ],
        "credentials_needed": [
            "Google Cloud project and Agent Builder app access",
            "GitLab base URL, project ID/path, and private token for real sync",
        ],
    }


@app.get("/api/v1/agent/sources")
def agent_sources(request: Request) -> dict:
    user = _require_agent_or_session_user(request)
    meeting_rows = list_meeting_results(MEETING_DB_PATH, user_id=int(user["user_id"]))
    live_items: list[dict[str, Any]] = []
    meetings: list[dict[str, Any]] = []

    for row in meeting_rows[:20]:
        meetings.append(_recorded_meeting_agent_context(row))

    output_root = PROJECT_ROOT / "output"
    live_dirs = sorted(output_root.glob("live-session-*"), key=lambda item: item.stat().st_mtime, reverse=True)
    for live_dir in live_dirs[:20]:
        session_id = live_dir.name.removeprefix("live-session-")
        try:
            record = _owned_live_session(session_id, user)
        except HTTPException:
            continue
        live_items.append(_live_agent_context(record))

    return {"items": {"meetings": meetings, "live": live_items}}


@app.get("/api/v1/agent/context/{source_kind}/{source_id}")
def agent_source_context(source_kind: str, source_id: str, request: Request) -> dict:
    user = _require_agent_or_session_user(request)
    return _resolve_agent_source_context(source_kind, source_id, user)


@app.post("/api/v1/agent/execution/preview")
async def agent_execution_preview(request: Request, payload: dict | None = None) -> dict:
    user = _require_agent_or_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    source_kind = str(request_payload.get("source_kind", "")).strip().lower()
    source_id = str(request_payload.get("source_id", "")).strip()
    assignee_map = request_payload.get("assignee_map", {})
    if not source_kind or not source_id:
        raise HTTPException(status_code=400, detail="source_kind and source_id are required.")

    context = _resolve_agent_source_context(source_kind, source_id, user)
    contract = context.get("agentic_contract", {}) or {}
    source = {
        "decisions": contract.get("entities", {}).get("decisions", []),
        "action_items": contract.get("entities", {}).get("actions", []),
        "problems": [
            {
                "text": item.get("description", ""),
                "timestamp": item.get("timestamp") or item.get("risk_id"),
                "speaker": item.get("speaker", "BoardSight"),
                "category": item.get("kind", "risk"),
            }
            for item in (contract.get("entities", {}).get("risk_signals", []) or [])
        ],
        "discussion_points": context.get("summary", {}).get("discussion_points", []),
    }
    plan = build_gitlab_execution_plan(
        source,
        source_kind=source_kind,
        source_id=source_id,
        meeting_title=str(context.get("title") or f"{source_kind}-{source_id}"),
        assignee_map=assignee_map if isinstance(assignee_map, dict) else {},
    )
    approval_record = create_agent_execution_run(
        AGENT_DB_PATH,
        source_kind=source_kind,
        source_id=source_id,
        meeting_title=str(context.get("title") or f"{source_kind}-{source_id}"),
        created_by_user_id=int(user["user_id"]),
        plan=plan,
    )
    return {
        "status": "previewed",
        "approval_required": True,
        "approval_id": approval_record.get("approval_id"),
        "plan": plan,
        "source_context": context,
    }


@app.get("/api/v1/agent/execution/{approval_id}")
def agent_execution_status(approval_id: str, request: Request) -> dict:
    _require_agent_or_session_user(request)
    record = get_agent_execution_run(AGENT_DB_PATH, approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent execution run not found.")
    return {
        "approval_id": record["approval_id"],
        "status": record["status"],
        "source_kind": record["source_kind"],
        "source_id": record["source_id"],
        "meeting_title": record["meeting_title"],
        "plan": record.get("plan_json") or {},
        "sync_result": record.get("sync_json"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


@app.post("/api/v1/agent/execution/approve")
async def agent_execution_approve(request: Request, payload: dict | None = None) -> dict:
    user = _require_agent_or_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    approval_id = str(request_payload.get("approval_id", "")).strip()
    if not approval_id:
        raise HTTPException(status_code=400, detail="approval_id is required.")
    record = get_agent_execution_run(AGENT_DB_PATH, approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent execution run not found.")

    connection = _resolve_agent_connection(request_payload)
    plan = record.get("plan_json") or {}
    runtime_config = default_config()
    sync_result = sync_plan_to_gitlab(plan, runtime_config, connection_overrides=connection)
    save_gitlab_sync(
        GITLAB_DB_PATH,
        source_kind=str(record.get("source_kind") or ""),
        source_id=str(record.get("source_id") or ""),
        project_ref=str(connection.get("project_id") or ""),
        dry_run=sync_result.get("status") != "synced",
        plan=plan,
        sync_result=sync_result,
    )
    updated = update_agent_execution_run(
        AGENT_DB_PATH,
        approval_id,
        status="synced" if sync_result.get("status") == "synced" else "dry-run-only",
        approved_by_user_id=int(user["user_id"]),
        connection=connection or None,
        sync_result=sync_result,
    )
    return {
        "approval_id": approval_id,
        "status": updated.get("status") if updated else "unknown",
        "plan": plan,
        "sync_result": sync_result,
    }


@app.post("/api/v1/chat/query")
async def chat_query(request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    question = str(request_payload.get("question", "") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required.")

    context = _resolve_chat_source_context(request_payload, user)
    structured_answer = _answer_from_structure(question, context)
    answer_source = "structured"
    answer = structured_answer

    if not answer:
        runtime_config = default_config()
        if runtime_config.llm_provider.strip().lower() == "extractive":
            answer = _grounded_chat_fallback(question, context)
            answer_source = "grounded-extractive"
        else:
            prompt = _build_chat_prompt(question, context)
            generated_text, generated_source = generate_text(prompt, runtime_config, max_new_tokens=120, min_new_tokens=20)
            if generated_text.strip():
                answer = generated_text.strip()
                answer_source = generated_source
            else:
                answer = _grounded_chat_fallback(question, context)
                answer_source = "grounded-fallback"

    return {
        "answer": answer,
        "answer_source": answer_source,
        "source": {
            "source_kind": context.get("source_kind"),
            "source_id": context.get("source_id"),
            "title": context.get("title"),
            "status": context.get("status"),
        },
        "counts": context.get("counts", {}),
    }


@app.post("/api/v1/gitlab/plan")
async def build_gitlab_plan(request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    source_kind = str(request_payload.get("source_kind", "")).strip().lower()
    source_id = str(request_payload.get("source_id", "")).strip()
    assignee_map = request_payload.get("assignee_map", {})
    if not source_kind or not source_id:
        raise HTTPException(status_code=400, detail="source_kind and source_id are required.")

    if source_kind == "live":
        record = _owned_live_session(source_id, user)
        source = {
            "decisions": record.get("state", {}).get("decisions", []),
            "action_items": record.get("state", {}).get("action_items", []),
            "problems": record.get("state", {}).get("problems", []),
            "discussion_points": record.get("state", {}).get("discussion_points", []),
        }
        meeting_title = str(record.get("title") or f"Live Meeting {source_id}")
    elif source_kind == "meeting":
        record = _resolve_owned_meeting_record(int(source_id), user)
        source, meeting_title = _recorded_meeting_to_execution_source(record)
    else:
        raise HTTPException(status_code=400, detail="source_kind must be 'live' or 'meeting'.")

    plan = build_gitlab_execution_plan(
        source,
        source_kind=source_kind,
        source_id=source_id,
        meeting_title=meeting_title,
        assignee_map=assignee_map if isinstance(assignee_map, dict) else {},
    )
    sync_id = save_gitlab_sync(
        GITLAB_DB_PATH,
        source_kind=source_kind,
        source_id=source_id,
        project_ref=str(request_payload.get("project_id", "") or ""),
        dry_run=True,
        plan=plan,
        sync_result=None,
    )
    return {"plan": plan, "sync_record_id": sync_id, "mode": "dry-run"}


@app.post("/api/v1/gitlab/sync")
async def sync_gitlab_plan(request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    source_kind = str(request_payload.get("source_kind", "")).strip().lower()
    source_id = str(request_payload.get("source_id", "")).strip()
    assignee_map = request_payload.get("assignee_map", {})
    connection = request_payload.get("connection", {})
    if not isinstance(connection, dict) or not connection:
        flat_connection = {
            "base_url": str(request_payload.get("gitlab_base_url", "") or "").strip(),
            "project_id": str(request_payload.get("gitlab_project_id", "") or "").strip(),
            "private_token": str(request_payload.get("gitlab_private_token", "") or "").strip(),
        }
        if any(flat_connection.values()):
            connection = flat_connection
    if not source_kind or not source_id:
        raise HTTPException(status_code=400, detail="source_kind and source_id are required.")

    if source_kind == "live":
        record = _owned_live_session(source_id, user)
        source = {
            "decisions": record.get("state", {}).get("decisions", []),
            "action_items": record.get("state", {}).get("action_items", []),
            "problems": record.get("state", {}).get("problems", []),
            "discussion_points": record.get("state", {}).get("discussion_points", []),
        }
        meeting_title = str(record.get("title") or f"Live Meeting {source_id}")
    elif source_kind == "meeting":
        record = _resolve_owned_meeting_record(int(source_id), user)
        source, meeting_title = _recorded_meeting_to_execution_source(record)
    else:
        raise HTTPException(status_code=400, detail="source_kind must be 'live' or 'meeting'.")

    plan = build_gitlab_execution_plan(
        source,
        source_kind=source_kind,
        source_id=source_id,
        meeting_title=meeting_title,
        assignee_map=assignee_map if isinstance(assignee_map, dict) else {},
    )
    runtime_config = default_config()
    sync_result = sync_plan_to_gitlab(plan, runtime_config, connection_overrides=connection if isinstance(connection, dict) else {})
    sync_id = save_gitlab_sync(
        GITLAB_DB_PATH,
        source_kind=source_kind,
        source_id=source_id,
        project_ref=str((connection or {}).get("project_id", "") if isinstance(connection, dict) else ""),
        dry_run=sync_result.get("status") != "synced",
        plan=plan,
        sync_result=sync_result,
    )
    return {"plan": plan, "sync_result": sync_result, "sync_record_id": sync_id}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
