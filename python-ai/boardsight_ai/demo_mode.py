from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from boardsight_ai.auth import create_session_for_user, create_user, init_auth_storage
from boardsight_ai.data_protection import encrypt_text
from boardsight_ai.database import execute, fetchall, fetchone
from boardsight_ai.models import PipelineResult, pipeline_result_from_dict
from boardsight_ai.storage import (
    append_live_session_event,
    append_live_visual_event,
    create_live_session,
    finalize_live_session,
    init_storage,
    save_live_copilot_reply,
    save_meeting_result,
)
from boardsight_ai.workspaces import ensure_personal_workspace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_TEMPLATE_ROOT = PROJECT_ROOT / "output" / "demo-mode"
DEMO_OUTPUT_ROOT = PROJECT_ROOT / "output" / "demo-workspace"
SAMPLE_RUN_PREFIX = "boardsight sample:"
SAMPLE_LIVE_TITLE = "boardsight sample: launch readiness live copilot"
PERMANENT_SAMPLE_USERNAMES = ("kashmira_admin", "kashmira_2704")


@dataclass(frozen=True)
class DemoMeetingSpec:
    slug: str
    title: str
    created_at: str
    payload: dict[str, Any]
    workflow_editor: dict[str, Any] | None = None


def demo_credentials() -> dict[str, str]:
    username = os.getenv("BOARDSIGHT_DEMO_USERNAME", "boardsight_demo").strip() or "boardsight_demo"
    password = os.getenv("BOARDSIGHT_DEMO_PASSWORD", "boardsight-demo-2026").strip() or "boardsight-demo-2026"
    email = os.getenv("BOARDSIGHT_DEMO_EMAIL", f"{username}@boardsight.local").strip().lower()
    display_name = os.getenv("BOARDSIGHT_DEMO_DISPLAY_NAME", "BoardSight Demo").strip() or "BoardSight Demo"
    return {
        "username": username,
        "password": password,
        "email": email,
        "display_name": display_name,
    }


def ensure_demo_workspace(
    auth_db_path: Path,
    meeting_db_path: Path,
    *,
    reset: bool = False,
    initialize: bool = True,
) -> dict[str, Any]:
    if initialize:
        init_auth_storage(auth_db_path)
        init_storage(meeting_db_path)
    demo_user = _upsert_demo_user(auth_db_path)
    workspace = ensure_personal_workspace(meeting_db_path, demo_user)
    organization_id = int(workspace["id"])
    if reset:
        _reset_demo_workspace(meeting_db_path, int(demo_user["user_id"]), organization_id)
    existing = _existing_demo_workspace(meeting_db_path, int(demo_user["user_id"]), organization_id)
    if existing is not None:
        return existing
    return _seed_demo_workspace(meeting_db_path, demo_user, organization_id=organization_id, include_live=True)


def ensure_permanent_sample_workspaces(
    auth_db_path: Path,
    meeting_db_path: Path,
    *,
    usernames: tuple[str, ...] = PERMANENT_SAMPLE_USERNAMES,
) -> dict[str, Any]:
    """Keep the golden-path samples available without modifying real meetings."""
    status: dict[str, Any] = {"seeded": [], "already_present": [], "missing_accounts": []}
    for username in usernames:
        user = _get_demo_user(auth_db_path, username)
        if user is None:
            status["missing_accounts"].append(username)
            continue
        workspace = ensure_personal_workspace(meeting_db_path, user)
        organization_id = int(workspace["id"])
        before = len(_sample_meeting_rows(meeting_db_path, int(user["user_id"]), organization_id))
        _seed_demo_workspace(meeting_db_path, user, organization_id=organization_id, include_live=False)
        target = "already_present" if before >= len(_demo_meeting_specs()) else "seeded"
        status[target].append(username)
    return status


def create_demo_session(
    auth_db_path: Path,
    meeting_db_path: Path,
    *,
    reset: bool = False,
    initialize: bool = True,
) -> dict[str, Any]:
    demo_manifest = ensure_demo_workspace(
        auth_db_path,
        meeting_db_path,
        reset=reset,
        initialize=initialize,
    )
    creds = demo_credentials()
    demo_user = _get_demo_user(auth_db_path, creds["username"])
    if demo_user is None:
        raise RuntimeError("Unable to create demo session.")
    # This public endpoint authenticates only the dedicated server-provisioned demo
    # identity, so an expensive password hash/verify cycle adds no security value.
    session = create_session_for_user(auth_db_path, demo_user)
    session["demo"] = demo_manifest
    return session


def _upsert_demo_user(auth_db_path: Path) -> dict[str, Any]:
    creds = demo_credentials()
    existing = _get_demo_user(auth_db_path, creds["username"])
    if existing is None:
        create_user(
            auth_db_path,
            creds["username"],
            creds["password"],
            role="admin",
            display_name=creds["display_name"],
            email=creds["email"],
            email_verified=True,
        )
    execute(
        auth_db_path,
        """
        UPDATE users
        SET email = :email,
            display_name = :display_name,
            role = 'admin',
            email_verified = :email_verified
        WHERE LOWER(username) = LOWER(:username)
        """,
        {
            "username": creds["username"],
            "email": creds["email"],
            "display_name": creds["display_name"],
            "email_verified": True,
        },
    )
    user = _get_demo_user(auth_db_path, creds["username"])
    if user is None:
        raise RuntimeError("Unable to provision demo user.")
    return user


def _get_demo_user(auth_db_path: Path, username: str) -> dict[str, Any] | None:
    row = fetchone(
        auth_db_path,
        """
        SELECT id, username, email, display_name, role, email_verified
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
        "email_verified": bool(row.get("email_verified")),
    }


def _sample_meeting_rows(meeting_db_path: Path, user_id: int, organization_id: int) -> list[dict[str, Any]]:
    return fetchall(
        meeting_db_path,
        """
        SELECT id, run_name
        FROM meetings
        WHERE user_id = :user_id
          AND organization_id = :organization_id
          AND LOWER(COALESCE(run_name, '')) LIKE :sample_prefix
        ORDER BY created_at DESC, id DESC
        """,
        {"user_id": user_id, "organization_id": organization_id, "sample_prefix": f"{SAMPLE_RUN_PREFIX}%"},
    )


def _existing_demo_workspace(meeting_db_path: Path, user_id: int, organization_id: int) -> dict[str, Any] | None:
    meeting_rows = _sample_meeting_rows(meeting_db_path, user_id, organization_id)
    live_row = fetchone(
        meeting_db_path,
        """
        SELECT id
        FROM live_sessions
        WHERE user_id = :user_id
          AND organization_id = :organization_id
        ORDER BY id DESC
        LIMIT 1
        """,
        {"user_id": user_id, "organization_id": organization_id},
    )
    if len(meeting_rows) < len(_demo_meeting_specs()) or live_row is None:
        return None
    featured = next((row for row in meeting_rows if "board review launch readiness" in str(row.get("run_name") or "")), meeting_rows[0])
    return {
        "workspaceName": "BoardSight Demo Workspace",
        "preferredView": "dashboard",
        "featuredMeetingId": int(featured["id"]),
        "meetingIds": [int(row["id"]) for row in meeting_rows],
        "liveSessionId": int(live_row["id"]),
        "guide": _demo_guide(),
    }


def _reset_demo_workspace(meeting_db_path: Path, user_id: int, organization_id: int) -> None:
    session_rows = fetchall(meeting_db_path, "SELECT id FROM live_sessions WHERE user_id = :user_id AND organization_id = :organization_id", {"user_id": user_id, "organization_id": organization_id})
    meeting_rows = _sample_meeting_rows(meeting_db_path, user_id, organization_id)
    session_ids = [int(row["id"]) for row in session_rows]
    meeting_ids = [int(row["id"]) for row in meeting_rows]
    for session_id in session_ids:
        execute(meeting_db_path, "DELETE FROM live_session_visual_events WHERE session_id = :session_id", {"session_id": session_id})
        execute(meeting_db_path, "DELETE FROM live_session_events WHERE session_id = :session_id", {"session_id": session_id})
    execute(meeting_db_path, "DELETE FROM live_sessions WHERE user_id = :user_id AND organization_id = :organization_id", {"user_id": user_id, "organization_id": organization_id})
    execute(meeting_db_path, "DELETE FROM meetings WHERE user_id = :user_id AND organization_id = :organization_id AND LOWER(COALESCE(run_name, '')) LIKE :sample_prefix", {"user_id": user_id, "organization_id": organization_id, "sample_prefix": f"{SAMPLE_RUN_PREFIX}%"})
    for source_id in [*meeting_ids, *session_ids]:
        execute(meeting_db_path, "DELETE FROM gitlab_syncs WHERE source_id = :source_id", {"source_id": str(source_id)})
    if DEMO_OUTPUT_ROOT.exists():
        shutil.rmtree(DEMO_OUTPUT_ROOT, ignore_errors=True)


def _seed_demo_workspace(meeting_db_path: Path, demo_user: dict[str, Any], *, organization_id: int, include_live: bool) -> dict[str, Any]:
    user_output_root = DEMO_OUTPUT_ROOT / str(demo_user["username"])
    user_output_root.mkdir(parents=True, exist_ok=True)
    user_id = int(demo_user["user_id"])
    username = str(demo_user["username"])

    meeting_ids: list[int] = []
    featured_meeting_id = 0
    for index, spec in enumerate(_demo_meeting_specs()):
        run_name = f"{SAMPLE_RUN_PREFIX} {spec.title}"
        existing = fetchone(
            meeting_db_path,
            "SELECT id FROM meetings WHERE user_id = :user_id AND organization_id = :organization_id AND LOWER(run_name) = LOWER(:run_name)",
            {"user_id": user_id, "organization_id": organization_id, "run_name": run_name},
        )
        if existing is not None:
            meeting_id = int(existing["id"])
            meeting_ids.append(meeting_id)
            if index == 0:
                featured_meeting_id = meeting_id
            continue
        output_dir = user_output_root / spec.slug
        output_dir.mkdir(parents=True, exist_ok=True)
        template_dir = DEMO_TEMPLATE_ROOT / spec.slug
        if template_dir.exists():
            shutil.copytree(template_dir, output_dir, dirs_exist_ok=True)
        result = pipeline_result_from_dict(spec.payload)
        result_file = output_dir / "boardsight_result.json"
        if not result_file.exists():
            result_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        performance_report = result.metadata.get("performance_report") if isinstance(result.metadata, dict) else {}
        performance_report_path = output_dir / "performance_report.json"
        if performance_report and not performance_report_path.exists():
            performance_report_path.write_text(json.dumps(performance_report, indent=2), encoding="utf-8")
        # Export files are generated on demand. Building every format here makes
        # the first Explore Demo click wait on PDF/DOCX/XLSX rendering.
        meeting_id = save_meeting_result(
            meeting_db_path,
            result,
            output_dir=output_dir,
            result_file=result_file,
            user_id=user_id,
            username=username,
            organization_id=organization_id,
        )
        execute(
            meeting_db_path,
            """
            UPDATE meetings
            SET run_name = :run_name,
                created_at = :created_at
            WHERE id = :meeting_id
            """,
            {"meeting_id": meeting_id, "run_name": run_name, "created_at": spec.created_at},
        )
        if spec.workflow_editor is not None:
            payload = result.to_dict()
            payload["workflow_editor"] = spec.workflow_editor
            execute(
                meeting_db_path,
                """
                UPDATE meetings
                SET result_json = :result_json
                WHERE id = :meeting_id
                """,
                {
                    "meeting_id": meeting_id,
                    "result_json": encrypt_text(json.dumps(payload)),
                },
            )
        meeting_ids.append(meeting_id)
        if index == 0:
            featured_meeting_id = meeting_id

    live_session_id = 0
    if include_live:
        live_row = fetchone(
            meeting_db_path,
            "SELECT id FROM live_sessions WHERE user_id = :user_id AND organization_id = :organization_id ORDER BY id DESC LIMIT 1",
            {"user_id": user_id, "organization_id": organization_id},
        )
        live_session_id = int(live_row["id"]) if live_row is not None else _seed_demo_live_session(
            meeting_db_path, user_id=user_id, username=username, organization_id=organization_id
        )
    return {
        "workspaceName": "BoardSight Demo Workspace",
        "preferredView": "dashboard",
        "featuredMeetingId": featured_meeting_id,
        "meetingIds": meeting_ids,
        "liveSessionId": live_session_id,
        "guide": _demo_guide(),
    }


def _seed_demo_live_session(meeting_db_path: Path, *, user_id: int, username: str, organization_id: int) -> int:
    session_id = create_live_session(meeting_db_path, SAMPLE_LIVE_TITLE, user_id=user_id, username=username, organization_id=organization_id)
    events = [
        (0.0, 10.0, "Kashmira Patil", "We are approving the July launch plan today, but the compliance API contract mismatch is still blocking release certification."),
        (10.0, 22.0, "Akanksha Rao", "I can own the GitLab follow-up tickets, but we need legal sign-off on the revised disclosures by Friday."),
        (22.0, 33.0, "Jordan Davis", "Decision made: proceed with the launch date, with a mandatory security checkpoint and a blocker review on Thursday."),
        (33.0, 44.0, "Maya Chen", "Action item: PMO will publish the readiness dashboard and assign owners for each blocker before end of day."),
        (44.0, 58.0, "Kashmira Patil", "Escalate the compliance gap to the board risk lane if the API fix is not merged by 3 PM tomorrow."),
    ]
    for start, end, speaker, text in events:
        append_live_session_event(
            meeting_db_path,
            session_id,
            text=text,
            speaker=speaker,
            start_seconds=start,
            end_seconds=end,
        )
    append_live_visual_event(
        meeting_db_path,
        session_id,
        timestamp_seconds=12.0,
        artifact_type="dashboard",
        display_mode="screen-share",
        visible_people_count=2,
        screen_present=True,
        chart_present=True,
        document_present=True,
        textual_content="Launch scorecard, blocker board, and release checklist are visible.",
        summary="The live share shows a launch readiness dashboard with red blocker markers and open owner fields.",
        confidence=0.92,
        detections=[{"label": "dashboard", "confidence": 0.92}, {"label": "risk-register", "confidence": 0.88}],
        source="demo-seed",
    )
    append_live_visual_event(
        meeting_db_path,
        session_id,
        timestamp_seconds=36.0,
        artifact_type="document",
        display_mode="hybrid",
        visible_people_count=4,
        screen_present=True,
        chart_present=False,
        document_present=True,
        textual_content="Compliance remediation plan with owners, dates, and escalation thresholds.",
        summary="A remediation document is presented while the team discusses legal sign-off and release conditions.",
        confidence=0.89,
        detections=[{"label": "document", "confidence": 0.89}, {"label": "person-speaking", "confidence": 0.77}],
        source="demo-seed",
    )
    save_live_copilot_reply(
        meeting_db_path,
        session_id,
        answer=(
            "BoardSight captured one launch approval, one escalation trigger, and two follow-through actions. "
            "The strongest blocker is the compliance API mismatch; assign a named owner in GitLab and review the status before Thursday's checkpoint."
        ),
        source="demo-seed-summary",
    )
    return session_id


def _demo_guide() -> list[str]:
    return [
        "Dashboard: start with the populated workspace metrics and recent meetings.",
        "Recorded meeting: open Board Review Launch Readiness to inspect decisions, blockers, workflow, and exports.",
        "Decision trace: review owners, rationale, timestamps, and the linked follow-through path.",
        "Workflow modelling: edit the seeded workflow nodes, notes, and descriptions to show collaborative refinement.",
        "Live copilot: open the active live session to review transcript updates and the GitLab assignment preview.",
    ]


def _demo_meeting_specs() -> list[DemoMeetingSpec]:
    now = datetime(2026, 7, 16, 17, 45, tzinfo=UTC)
    return [
        DemoMeetingSpec(
            slug="board-review-launch-readiness",
            title="board review launch readiness",
            created_at=(now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            payload=_build_primary_meeting_payload(),
            workflow_editor=_build_primary_workflow_editor(),
        ),
        DemoMeetingSpec(
            slug="compliance-risk-follow-up",
            title="compliance risk follow up",
            created_at=(now - timedelta(days=1, hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            payload=_build_compliance_follow_up_payload(),
        ),
        DemoMeetingSpec(
            slug="product-launch-pmo-sync",
            title="product launch pmo sync",
            created_at=(now - timedelta(days=2, hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
            payload=_build_pmo_sync_payload(),
        ),
    ]


def _build_primary_meeting_payload() -> dict[str, Any]:
    return {
        "input_video": str(DEMO_OUTPUT_ROOT / "board-review-launch-readiness" / "board_review_launch_readiness.mp4"),
        "transcript": {
            "full_text": "\n".join(
                [
                    "[0.0-18.0] Kashmira Patil (CEO): We need a final recommendation on the July product launch, including the compliance exposure and readiness dashboard.",
                    "[18.0-35.0] Jordan Davis (Board Observer): The board wants a clear decision, named owners, and a trigger for escalation if the API contract issue is not resolved.",
                    "[35.0-56.0] Maya Chen (PMO Lead): The launch plan is green except for disclosure sign-off and the GitLab backlog for security follow-through.",
                    "[56.0-77.0] Akanksha Rao (Engineering Lead): I will own the GitLab assignments, but QA is blocked until the compliance API mismatch is merged.",
                    "[77.0-96.0] Ravi Mehta (Compliance): Legal can sign off by Friday if the revised disclosure appendix is circulated today.",
                    "[96.0-116.0] Kashmira Patil (CEO): Decision one: hold the launch date. Decision two: require a Thursday blocker review. Decision three: escalate to the risk committee if the API fix misses tomorrow 3 PM.",
                    "[116.0-134.0] Maya Chen (PMO Lead): I will publish the readiness dashboard and assign owners for every open action before end of day.",
                    "[134.0-154.0] Jordan Davis (Board Observer): Capture the rationale, the escalation trigger, and the evidence trail in the BoardSight export for the board packet.",
                ]
            ),
            "segments": [
                {"start": 0.0, "end": 18.0, "speaker": "Kashmira Patil (CEO)", "text": "We need a final recommendation on the July product launch, including the compliance exposure and readiness dashboard.", "confidence": 0.95},
                {"start": 18.0, "end": 35.0, "speaker": "Jordan Davis (Board Observer)", "text": "The board wants a clear decision, named owners, and a trigger for escalation if the API contract issue is not resolved.", "confidence": 0.93},
                {"start": 35.0, "end": 56.0, "speaker": "Maya Chen (PMO Lead)", "text": "The launch plan is green except for disclosure sign-off and the GitLab backlog for security follow-through.", "confidence": 0.94},
                {"start": 56.0, "end": 77.0, "speaker": "Akanksha Rao (Engineering Lead)", "text": "I will own the GitLab assignments, but QA is blocked until the compliance API mismatch is merged.", "confidence": 0.96},
                {"start": 77.0, "end": 96.0, "speaker": "Ravi Mehta (Compliance)", "text": "Legal can sign off by Friday if the revised disclosure appendix is circulated today.", "confidence": 0.92},
                {"start": 96.0, "end": 116.0, "speaker": "Kashmira Patil (CEO)", "text": "Decision one: hold the launch date. Decision two: require a Thursday blocker review. Decision three: escalate to the risk committee if the API fix misses tomorrow 3 PM.", "confidence": 0.97},
                {"start": 116.0, "end": 134.0, "speaker": "Maya Chen (PMO Lead)", "text": "I will publish the readiness dashboard and assign owners for every open action before end of day.", "confidence": 0.94},
                {"start": 134.0, "end": 154.0, "speaker": "Jordan Davis (Board Observer)", "text": "Capture the rationale, the escalation trigger, and the evidence trail in the BoardSight export for the board packet.", "confidence": 0.91},
            ],
            "speaker_directory": [
                {"speaker_id": "spk-kashmira", "display_name": "Kashmira Patil", "designation": "CEO", "report_label": "Kashmira Patil (CEO)"},
                {"speaker_id": "spk-jordan", "display_name": "Jordan Davis", "designation": "Board Observer", "report_label": "Jordan Davis (Board Observer)"},
                {"speaker_id": "spk-maya", "display_name": "Maya Chen", "designation": "PMO Lead", "report_label": "Maya Chen (PMO Lead)"},
                {"speaker_id": "spk-akanksha", "display_name": "Akanksha Rao", "designation": "Engineering Lead", "report_label": "Akanksha Rao (Engineering Lead)"},
                {"speaker_id": "spk-ravi", "display_name": "Ravi Mehta", "designation": "Compliance", "report_label": "Ravi Mehta (Compliance)"},
            ],
        },
        "speaker_dominance": {
            "speakers": [
                {"speaker": "Kashmira Patil (CEO)", "talk_time_sec": 38.0, "dominance_ratio": 24.7, "face_recognition_ready": True},
                {"speaker": "Maya Chen (PMO Lead)", "talk_time_sec": 39.0, "dominance_ratio": 25.3, "face_recognition_ready": True},
                {"speaker": "Akanksha Rao (Engineering Lead)", "talk_time_sec": 21.0, "dominance_ratio": 13.6, "face_recognition_ready": True},
                {"speaker": "Jordan Davis (Board Observer)", "talk_time_sec": 37.0, "dominance_ratio": 24.0, "face_recognition_ready": True},
                {"speaker": "Ravi Mehta (Compliance)", "talk_time_sec": 19.0, "dominance_ratio": 12.4, "face_recognition_ready": True},
            ],
            "active_speaker_timeline": [
                {"start": 0.0, "end": 18.0, "speaker": "Kashmira Patil (CEO)", "source": "audio-dominance"},
                {"start": 18.0, "end": 35.0, "speaker": "Jordan Davis (Board Observer)", "source": "audio-dominance"},
                {"start": 35.0, "end": 56.0, "speaker": "Maya Chen (PMO Lead)", "source": "audio-dominance"},
                {"start": 56.0, "end": 77.0, "speaker": "Akanksha Rao (Engineering Lead)", "source": "audio-dominance"},
                {"start": 77.0, "end": 96.0, "speaker": "Ravi Mehta (Compliance)", "source": "audio-dominance"},
                {"start": 96.0, "end": 116.0, "speaker": "Kashmira Patil (CEO)", "source": "audio-dominance"},
                {"start": 116.0, "end": 134.0, "speaker": "Maya Chen (PMO Lead)", "source": "audio-dominance"},
                {"start": 134.0, "end": 154.0, "speaker": "Jordan Davis (Board Observer)", "source": "audio-dominance"},
            ],
            "visual_identities": [
                {"identity_id": "face-kashmira", "label": "Kashmira Patil", "tracking_mode": "demo-visual-identity", "bbox": [122, 85, 60, 60]},
                {"identity_id": "face-maya", "label": "Maya Chen", "tracking_mode": "demo-visual-identity", "bbox": [330, 92, 58, 58]},
                {"identity_id": "face-akanksha", "label": "Akanksha Rao", "tracking_mode": "demo-visual-identity", "bbox": [522, 90, 58, 58]},
            ],
        },
        "decision_moments": [
            {"event_id": "DM-1", "timestamp": "01:36", "speaker": "Kashmira Patil (CEO)", "text": "Hold the July launch date and continue execution against the current release plan.", "confidence": 0.96, "label": "decision", "evidence": ["explicit board approval", "speaker declared final recommendation"]},
            {"event_id": "DM-2", "timestamp": "01:42", "speaker": "Kashmira Patil (CEO)", "text": "Run a mandatory blocker review on Thursday before final go-live sign-off.", "confidence": 0.94, "label": "decision", "evidence": ["deadline stated", "follow-through requirement"]},
            {"event_id": "DM-3", "timestamp": "01:49", "speaker": "Kashmira Patil (CEO)", "text": "Escalate to the risk committee if the API contract fix misses tomorrow 3 PM.", "confidence": 0.95, "label": "decision", "evidence": ["escalation trigger", "time-bound risk condition"]},
            {"event_id": "AI-1", "timestamp": "01:56", "speaker": "Maya Chen (PMO Lead)", "text": "Publish the readiness dashboard and assign owners for every open action before end of day.", "confidence": 0.92, "label": "action", "evidence": ["named owner", "deadline end of day"]},
            {"event_id": "BL-1", "timestamp": "00:56", "speaker": "Akanksha Rao (Engineering Lead)", "text": "QA remains blocked until the compliance API mismatch is merged.", "confidence": 0.91, "label": "blocker", "evidence": ["blocked release certification", "dependency unresolved"]},
        ],
        "visual_artifacts": [
            {"artifact_id": "VA-1", "start_time": 12.0, "end_time": 38.0, "artifact_type": "dashboard", "confidence": 0.93, "detections": [{"label": "launch scorecard", "confidence": 0.91}], "display_mode": "screen-share", "content_summary": "Launch readiness scorecard with red blocker flags.", "content_text": "Readiness dashboard, owner tracker, blocker board.", "content_insight": "The visual evidence emphasizes that execution readiness is high but one blocker remains unresolved."},
            {"artifact_id": "VA-2", "start_time": 40.0, "end_time": 82.0, "artifact_type": "document", "confidence": 0.88, "detections": [{"label": "compliance appendix", "confidence": 0.86}], "display_mode": "hybrid", "content_summary": "Disclosure appendix and legal sign-off checklist.", "content_text": "Legal requirements, disclosure appendix, owner checklist.", "content_insight": "Compliance sign-off is time-bound and directly connected to launch approval."},
            {"artifact_id": "VA-3", "start_time": 90.0, "end_time": 140.0, "artifact_type": "chart", "confidence": 0.85, "detections": [{"label": "risk trend", "confidence": 0.84}], "display_mode": "presentation", "content_summary": "Risk trend chart and escalation matrix.", "content_text": "Risk lane, threshold trigger, escalation matrix.", "content_insight": "The chart supports the decision to escalate only if the API fix misses the hard cutoff."},
        ],
        "workflow_model": {
            "stages": [
                {"timestamp": 0.0, "stage": "frame", "speaker": "Kashmira Patil (CEO)", "summary": "Frame the launch decision and risk exposure for the board review."},
                {"timestamp": 35.0, "stage": "review", "speaker": "Maya Chen (PMO Lead)", "summary": "Review readiness dashboard, blocker board, and open GitLab backlog."},
                {"timestamp": 77.0, "stage": "compliance-check", "speaker": "Ravi Mehta (Compliance)", "summary": "Validate disclosure sign-off conditions and legal timing."},
                {"timestamp": 96.0, "stage": "decision", "speaker": "Kashmira Patil (CEO)", "summary": "Approve launch path with blocker checkpoint and escalation condition."},
                {"timestamp": 116.0, "stage": "follow-through", "speaker": "Maya Chen (PMO Lead)", "summary": "Assign owners, publish dashboard, and document rationale for the board packet."},
            ],
            "transitions": [
                {"from": "frame", "to": "review", "condition": "launch context established"},
                {"from": "review", "to": "compliance-check", "condition": "blockers isolated"},
                {"from": "compliance-check", "to": "decision", "condition": "legal timing clarified"},
                {"from": "decision", "to": "follow-through", "condition": "owners and escalation trigger confirmed"},
            ],
            "bottlenecks": [
                "QA cannot complete release certification until the compliance API contract mismatch is merged.",
                "Legal sign-off remains pending until the revised disclosure appendix is circulated and acknowledged.",
            ],
            "prioritized_decisions": [
                {
                    "decision_id": "DEC-101",
                    "title": "Hold July launch date",
                    "text": "Maintain the July launch date and continue execution against the current release plan.",
                    "owner": "Kashmira Patil",
                    "timestamp": "01:36",
                    "rationale": "The launch plan is broadly green and the remaining blocker has a contained escalation path.",
                    "evidence": ["dashboard status green except one blocker", "board observer requested explicit go-forward call"],
                    "urgency": "High",
                    "impact": "Strategic",
                    "blockers": ["Compliance API mismatch"],
                    "next_action": "Track the blocker through Thursday's checkpoint.",
                    "status": "Approved",
                    "priority_score": 0.94,
                    "confidence": 0.95,
                    "linked_gitlab_issue": "https://gitlab.example.com/boardsight/demo/-/issues/241",
                },
                {
                    "decision_id": "DEC-102",
                    "title": "Require Thursday blocker review",
                    "text": "Run a mandatory blocker review on Thursday before final go-live sign-off.",
                    "owner": "Maya Chen",
                    "timestamp": "01:42",
                    "rationale": "A structured checkpoint prevents silent slippage on the only unresolved dependency.",
                    "evidence": ["follow-through requirement stated by CEO", "PMO readiness dashboard available"],
                    "urgency": "High",
                    "impact": "Operational",
                    "blockers": ["Open owner updates"],
                    "next_action": "Publish the blocker review agenda and owner list.",
                    "status": "Scheduled",
                    "priority_score": 0.88,
                    "confidence": 0.92,
                    "linked_gitlab_issue": "https://gitlab.example.com/boardsight/demo/-/issues/242",
                },
                {
                    "decision_id": "DEC-103",
                    "title": "Escalate on missed API fix cutoff",
                    "text": "Escalate to the risk committee if the API contract fix misses tomorrow 3 PM.",
                    "owner": "Jordan Davis",
                    "timestamp": "01:49",
                    "rationale": "The board wants a hard trigger instead of an open-ended risk discussion.",
                    "evidence": ["time-bound escalation trigger", "risk lane chart shown"],
                    "urgency": "Critical",
                    "impact": "Risk",
                    "blockers": ["Engineering dependency unresolved"],
                    "next_action": "Monitor merge status and prepare escalation note template.",
                    "status": "Watch",
                    "priority_score": 0.91,
                    "confidence": 0.94,
                    "linked_gitlab_issue": "https://gitlab.example.com/boardsight/demo/-/issues/243",
                },
            ],
            "execution_plan": [
                {
                    "action_id": "ACT-201",
                    "title": "Publish launch readiness dashboard",
                    "owner": "Maya Chen",
                    "due_hint": "Today 18:00 IST",
                    "priority_score": 0.91,
                    "decision_id": "DEC-101",
                    "dependencies": ["Updated owner list", "Latest blocker statuses"],
                    "blocker_flag": False,
                    "status": "In progress",
                    "notes": "Board packet should link directly to the latest dashboard snapshot.",
                    "gitlab_issue_url": "https://gitlab.example.com/boardsight/demo/-/issues/251",
                },
                {
                    "action_id": "ACT-202",
                    "title": "Assign GitLab follow-up tickets",
                    "owner": "Akanksha Rao",
                    "due_hint": "Today 17:30 IST",
                    "priority_score": 0.89,
                    "decision_id": "DEC-102",
                    "dependencies": ["Action register confirmed"],
                    "blocker_flag": False,
                    "status": "Ready",
                    "notes": "Create tickets for API fix, QA unblock, and disclosure appendix validation.",
                    "gitlab_issue_url": "https://gitlab.example.com/boardsight/demo/-/issues/252",
                },
                {
                    "action_id": "ACT-203",
                    "title": "Merge compliance API contract fix",
                    "owner": "Akanksha Rao",
                    "due_hint": "Tomorrow 15:00 IST",
                    "priority_score": 0.96,
                    "decision_id": "DEC-103",
                    "dependencies": ["QA validation", "Security regression check"],
                    "blocker_flag": True,
                    "status": "Blocked",
                    "notes": "This is the hard escalation trigger for the risk committee path.",
                    "gitlab_issue_url": "https://gitlab.example.com/boardsight/demo/-/issues/253",
                },
                {
                    "action_id": "ACT-204",
                    "title": "Circulate revised disclosure appendix",
                    "owner": "Ravi Mehta",
                    "due_hint": "Friday 12:00 IST",
                    "priority_score": 0.83,
                    "decision_id": "DEC-101",
                    "dependencies": ["Legal review complete"],
                    "blocker_flag": False,
                    "status": "Queued",
                    "notes": "Attach version-controlled appendix to the board packet.",
                    "gitlab_issue_url": "https://gitlab.example.com/boardsight/demo/-/issues/254",
                },
                {
                    "action_id": "ACT-205",
                    "title": "Prepare Thursday blocker review brief",
                    "owner": "Jordan Davis",
                    "due_hint": "Thursday 10:00 IST",
                    "priority_score": 0.8,
                    "decision_id": "DEC-102",
                    "dependencies": ["Dashboard published", "Owners confirmed"],
                    "blocker_flag": False,
                    "status": "Ready",
                    "notes": "Summarize blocker movements, risk posture, and missing owners.",
                    "gitlab_issue_url": "https://gitlab.example.com/boardsight/demo/-/issues/255",
                },
                {
                    "action_id": "ACT-206",
                    "title": "Draft risk committee escalation note",
                    "owner": "Kashmira Patil",
                    "due_hint": "Tomorrow 14:00 IST",
                    "priority_score": 0.78,
                    "decision_id": "DEC-103",
                    "dependencies": ["API fix status update"],
                    "blocker_flag": False,
                    "status": "Standby",
                    "notes": "Only send if the engineering merge misses the agreed cutoff.",
                    "gitlab_issue_url": "https://gitlab.example.com/boardsight/demo/-/issues/256",
                },
            ],
            "workflow_summary": {
                "status": "decision-ready",
                "top_priority_decision": "Hold July launch date with a hard risk escalation trigger.",
                "source": "boardsight-demo-seed",
            },
        },
        "decision_traces": [
            {
                "trace_id": "TRACE-301",
                "title": "Launch date approval",
                "summary": "The board accepted the current launch plan after reviewing the readiness dashboard and narrowing the open risk to one engineering dependency.",
                "owner": "Kashmira Patil",
                "rationale": ["The readiness dashboard showed broad execution health.", "The blocker had a bounded escalation path and named engineering owner."],
                "next_steps": ["Track Thursday blocker review.", "Confirm disclosure appendix circulation."],
                "related_artifacts": ["VA-1", "VA-3"],
                "priority_score": 0.94,
                "decision_type": "approval",
                "supporting_speakers": ["Jordan Davis", "Maya Chen"],
                "execution_tasks": [{"action_id": "ACT-201"}, {"action_id": "ACT-205"}],
            },
            {
                "trace_id": "TRACE-302",
                "title": "Blocker review checkpoint",
                "summary": "A formal Thursday checkpoint was introduced to prevent the final launch call from resting on stale blocker assumptions.",
                "owner": "Maya Chen",
                "rationale": ["The open dependency could change quickly.", "Board governance required named owners and a scheduled review."],
                "next_steps": ["Publish checkpoint agenda.", "Confirm all owners before end of day."],
                "related_artifacts": ["VA-1"],
                "priority_score": 0.88,
                "decision_type": "governance-checkpoint",
                "supporting_speakers": ["Kashmira Patil", "Jordan Davis"],
                "execution_tasks": [{"action_id": "ACT-205"}],
            },
            {
                "trace_id": "TRACE-303",
                "title": "Risk committee escalation trigger",
                "summary": "The team established a hard escalation path if the API contract mismatch remained unresolved after the agreed engineering cutoff.",
                "owner": "Jordan Davis",
                "rationale": ["The board asked for a non-ambiguous escalation threshold.", "The risk trend chart showed the dependency as the only critical open item."],
                "next_steps": ["Monitor merge status tomorrow.", "Send escalation note if 3 PM cutoff is missed."],
                "related_artifacts": ["VA-3"],
                "priority_score": 0.91,
                "decision_type": "risk-escalation",
                "supporting_speakers": ["Akanksha Rao", "Ravi Mehta"],
                "execution_tasks": [{"action_id": "ACT-203"}, {"action_id": "ACT-206"}],
            },
        ],
        "attention_sentiment": {
            "overall_attention": 82.6,
            "overall_sentiment": "positive",
            "engagement_timeline": [
                {"timestamp": "00:20", "attention": 78.0},
                {"timestamp": "01:10", "attention": 84.0},
                {"timestamp": "02:10", "attention": 86.0},
            ],
            "sentiment_timeline": [
                {"timestamp": "00:20", "sentiment": "focused"},
                {"timestamp": "01:10", "sentiment": "constructive"},
                {"timestamp": "02:10", "sentiment": "decisive"},
            ],
            "cognitive_rating": {"focus": 84.0, "clarity": 88.0, "overload_risk": 24.0, "meeting_focus": 84.0, "meeting_clarity": 88.0},
            "participant_states": [
                {"speaker": "Kashmira Patil", "state": "driving"},
                {"speaker": "Maya Chen", "state": "coordinating"},
                {"speaker": "Akanksha Rao", "state": "blocked-owner"},
            ],
            "model_sources": ["demo-governance-seed", "transcript-execution-heuristic"],
            "coverage_ratio": 0.94,
        },
        "meeting_scores": {
            "impact_score": 91.0,
            "productivity_score": 88.0,
            "execution_readiness": 79.0,
            "speaker_rating": {
                "Kashmira Patil": "High clarity",
                "Maya Chen": "High operational detail",
                "Akanksha Rao": "Critical dependency owner",
                "Jordan Davis": "Governance guardrail",
            },
            "cognitive_rating": {"focus": 84.0, "clarity": 88.0, "overload_risk": 24.0, "meeting_focus": 84.0, "meeting_clarity": 88.0},
            "meeting_conclusion": "Launch stays on schedule, but the compliance API mismatch remains the decisive blocker and carries a hard escalation trigger.",
        },
        "warnings": [],
        "metadata": {
            "analysis_profile": "enterprise-demo",
            "source_mode": "recorded-import",
            "data_contract_version": "boardsight-demo-v1",
            "performance_report": {"runtime_profile": "demo-precomputed", "stage_timings_seconds": {"transcript": 5.1, "workflow": 1.2, "reports": 0.8}},
            "agentic_contract": {
                "contract_version": "demo-contract-v1",
                "entities": {
                    "risk_signals": [
                        {"id": "RISK-1", "severity": "high", "summary": "Compliance API mismatch blocks QA."},
                        {"id": "RISK-2", "severity": "medium", "summary": "Legal sign-off pending on disclosure appendix."},
                    ]
                },
            },
        },
    }


def _build_compliance_follow_up_payload() -> dict[str, Any]:
    return {
        "input_video": str(DEMO_OUTPUT_ROOT / "compliance-risk-follow-up" / "compliance_follow_up.mp4"),
        "transcript": {
            "full_text": "[0.0-18.0] Ravi Mehta (Compliance): The disclosure appendix is drafted, but we still need engineering evidence for the API contract update.\n[18.0-36.0] Akanksha Rao (Engineering Lead): The merge request is ready and QA can validate tonight once the final schema lands.\n[36.0-52.0] Kashmira Patil (CEO): Decision: keep the launch path open, but escalate to legal immediately if validation slips beyond tonight.\n[52.0-68.0] Maya Chen (PMO Lead): Action: update the risk register and publish a short follow-up note to the board observers.",
            "segments": [
                {"start": 0.0, "end": 18.0, "speaker": "Ravi Mehta (Compliance)", "text": "The disclosure appendix is drafted, but we still need engineering evidence for the API contract update.", "confidence": 0.93},
                {"start": 18.0, "end": 36.0, "speaker": "Akanksha Rao (Engineering Lead)", "text": "The merge request is ready and QA can validate tonight once the final schema lands.", "confidence": 0.94},
                {"start": 36.0, "end": 52.0, "speaker": "Kashmira Patil (CEO)", "text": "Decision: keep the launch path open, but escalate to legal immediately if validation slips beyond tonight.", "confidence": 0.95},
                {"start": 52.0, "end": 68.0, "speaker": "Maya Chen (PMO Lead)", "text": "Action: update the risk register and publish a short follow-up note to the board observers.", "confidence": 0.92},
            ],
            "speaker_directory": [
                {"speaker_id": "spk-ravi", "display_name": "Ravi Mehta", "designation": "Compliance", "report_label": "Ravi Mehta (Compliance)"},
                {"speaker_id": "spk-akanksha", "display_name": "Akanksha Rao", "designation": "Engineering Lead", "report_label": "Akanksha Rao (Engineering Lead)"},
                {"speaker_id": "spk-kashmira", "display_name": "Kashmira Patil", "designation": "CEO", "report_label": "Kashmira Patil (CEO)"},
                {"speaker_id": "spk-maya", "display_name": "Maya Chen", "designation": "PMO Lead", "report_label": "Maya Chen (PMO Lead)"},
            ],
        },
        "speaker_dominance": {
            "speakers": [
                {"speaker": "Ravi Mehta (Compliance)", "talk_time_sec": 18.0, "dominance_ratio": 26.4, "face_recognition_ready": True},
                {"speaker": "Akanksha Rao (Engineering Lead)", "talk_time_sec": 18.0, "dominance_ratio": 26.4, "face_recognition_ready": True},
                {"speaker": "Kashmira Patil (CEO)", "talk_time_sec": 16.0, "dominance_ratio": 23.5, "face_recognition_ready": True},
                {"speaker": "Maya Chen (PMO Lead)", "talk_time_sec": 16.0, "dominance_ratio": 23.5, "face_recognition_ready": True},
            ],
            "active_speaker_timeline": [
                {"start": 0.0, "end": 18.0, "speaker": "Ravi Mehta (Compliance)", "source": "audio-dominance"},
                {"start": 18.0, "end": 36.0, "speaker": "Akanksha Rao (Engineering Lead)", "source": "audio-dominance"},
                {"start": 36.0, "end": 52.0, "speaker": "Kashmira Patil (CEO)", "source": "audio-dominance"},
                {"start": 52.0, "end": 68.0, "speaker": "Maya Chen (PMO Lead)", "source": "audio-dominance"},
            ],
            "visual_identities": [],
        },
        "decision_moments": [
            {"event_id": "DM-21", "timestamp": "00:36", "speaker": "Kashmira Patil (CEO)", "text": "Keep the launch path open, but escalate to legal immediately if validation slips beyond tonight.", "confidence": 0.93, "label": "decision", "evidence": ["explicit decision statement"]},
            {"event_id": "AI-21", "timestamp": "00:52", "speaker": "Maya Chen (PMO Lead)", "text": "Update the risk register and publish a short follow-up note to the board observers.", "confidence": 0.9, "label": "action", "evidence": ["named task with owner"]},
            {"event_id": "BL-21", "timestamp": "00:18", "speaker": "Akanksha Rao (Engineering Lead)", "text": "QA can validate tonight once the final schema lands.", "confidence": 0.88, "label": "blocker", "evidence": ["dependency on schema landing"]},
        ],
        "visual_artifacts": [
            {"artifact_id": "VA-21", "start_time": 5.0, "end_time": 30.0, "artifact_type": "document", "confidence": 0.84, "detections": [], "display_mode": "screen-share", "content_summary": "Risk register update sheet.", "content_text": "Open legal items and schema validation checklist.", "content_insight": "The follow-up meeting is focused on clearing the remaining compliance evidence."},
        ],
        "workflow_model": {
            "stages": [
                {"timestamp": 0.0, "stage": "review", "speaker": "Ravi Mehta (Compliance)", "summary": "Review compliance evidence and final engineering proof."},
                {"timestamp": 36.0, "stage": "decision", "speaker": "Kashmira Patil (CEO)", "summary": "Approve conditional continuation with escalation path."},
                {"timestamp": 52.0, "stage": "follow-through", "speaker": "Maya Chen (PMO Lead)", "summary": "Document risk update and notify board observers."},
            ],
            "transitions": [{"from": "review", "to": "decision", "condition": "validation timing understood"}, {"from": "decision", "to": "follow-through", "condition": "owner assigned"}],
            "bottlenecks": ["Validation depends on the final schema landing tonight."],
            "prioritized_decisions": [
                {"decision_id": "DEC-201", "title": "Conditional continuation", "text": "Keep the launch path open pending tonight's validation.", "owner": "Kashmira Patil", "timestamp": "00:36", "rationale": "Validation is expected tonight and no other blockers remain.", "evidence": ["engineering merge ready"], "urgency": "High", "impact": "Operational", "blockers": ["Final schema landing"], "next_action": "Monitor nightly validation.", "status": "Conditional", "priority_score": 0.82, "confidence": 0.9},
            ],
            "execution_plan": [
                {"action_id": "ACT-221", "title": "Update risk register", "owner": "Maya Chen", "due_hint": "Tonight", "priority_score": 0.78, "decision_id": "DEC-201", "dependencies": ["Validation status"], "blocker_flag": False, "status": "Ready", "notes": "Push final note to board observers."},
                {"action_id": "ACT-222", "title": "Validate merged schema", "owner": "Akanksha Rao", "due_hint": "Tonight", "priority_score": 0.9, "decision_id": "DEC-201", "dependencies": ["Merge complete"], "blocker_flag": True, "status": "Blocked", "notes": "Release path depends on this."},
            ],
            "workflow_summary": {"status": "conditional", "top_priority_decision": "Keep launch path open pending validation.", "source": "boardsight-demo-seed"},
        },
        "decision_traces": [
            {"trace_id": "TRACE-221", "title": "Conditional continuation", "summary": "The team kept the launch path open while waiting on the final schema validation.", "owner": "Kashmira Patil", "rationale": ["Only one dependency remained.", "Engineering had a clear tonight target."], "next_steps": ["Confirm nightly validation.", "Escalate if delayed."], "related_artifacts": ["VA-21"], "priority_score": 0.82, "decision_type": "conditional-approval", "supporting_speakers": ["Ravi Mehta", "Akanksha Rao"], "execution_tasks": [{"action_id": "ACT-222"}]},
        ],
        "attention_sentiment": {
            "overall_attention": 76.4,
            "overall_sentiment": "focused",
            "engagement_timeline": [{"timestamp": "00:20", "attention": 75.0}, {"timestamp": "00:48", "attention": 78.0}],
            "sentiment_timeline": [{"timestamp": "00:20", "sentiment": "focused"}, {"timestamp": "00:48", "sentiment": "constructive"}],
            "cognitive_rating": {"focus": 77.0, "clarity": 80.0, "overload_risk": 28.0, "meeting_focus": 77.0, "meeting_clarity": 80.0},
            "participant_states": [],
            "model_sources": ["boardsight-demo-seed"],
            "coverage_ratio": 0.9,
        },
        "meeting_scores": {
            "impact_score": 78.0,
            "productivity_score": 81.0,
            "execution_readiness": 68.0,
            "speaker_rating": {"Kashmira Patil": "Decisive", "Akanksha Rao": "Dependency owner"},
            "cognitive_rating": {"focus": 77.0, "clarity": 80.0, "overload_risk": 28.0, "meeting_focus": 77.0, "meeting_clarity": 80.0},
            "meeting_conclusion": "The team kept the launch path open while waiting on the last engineering validation checkpoint.",
        },
        "warnings": [],
        "metadata": {"analysis_profile": "enterprise-demo", "source_mode": "recorded-import", "data_contract_version": "boardsight-demo-v1", "performance_report": {"runtime_profile": "demo-precomputed"}},
    }


def _build_pmo_sync_payload() -> dict[str, Any]:
    return {
        "input_video": str(DEMO_OUTPUT_ROOT / "product-launch-pmo-sync" / "product_launch_pmo_sync.mp4"),
        "transcript": {
            "full_text": "[0.0-16.0] Maya Chen (PMO Lead): Today we are walking the action register, owners, and deadlines for the launch follow-through.\n[16.0-31.0] Jordan Davis (Board Observer): The board wants every open action tied back to a decision and a reporting line.\n[31.0-47.0] Akanksha Rao (Engineering Lead): Engineering can close three actions today, but the deployment checklist still needs a final sign-off.\n[47.0-63.0] Maya Chen (PMO Lead): Action: update the workflow model and export a clean follow-through pack by this evening.",
            "segments": [
                {"start": 0.0, "end": 16.0, "speaker": "Maya Chen (PMO Lead)", "text": "Today we are walking the action register, owners, and deadlines for the launch follow-through.", "confidence": 0.93},
                {"start": 16.0, "end": 31.0, "speaker": "Jordan Davis (Board Observer)", "text": "The board wants every open action tied back to a decision and a reporting line.", "confidence": 0.91},
                {"start": 31.0, "end": 47.0, "speaker": "Akanksha Rao (Engineering Lead)", "text": "Engineering can close three actions today, but the deployment checklist still needs a final sign-off.", "confidence": 0.92},
                {"start": 47.0, "end": 63.0, "speaker": "Maya Chen (PMO Lead)", "text": "Action: update the workflow model and export a clean follow-through pack by this evening.", "confidence": 0.94},
            ],
            "speaker_directory": [
                {"speaker_id": "spk-maya", "display_name": "Maya Chen", "designation": "PMO Lead", "report_label": "Maya Chen (PMO Lead)"},
                {"speaker_id": "spk-jordan", "display_name": "Jordan Davis", "designation": "Board Observer", "report_label": "Jordan Davis (Board Observer)"},
                {"speaker_id": "spk-akanksha", "display_name": "Akanksha Rao", "designation": "Engineering Lead", "report_label": "Akanksha Rao (Engineering Lead)"},
            ],
        },
        "speaker_dominance": {
            "speakers": [
                {"speaker": "Maya Chen (PMO Lead)", "talk_time_sec": 32.0, "dominance_ratio": 50.8, "face_recognition_ready": True},
                {"speaker": "Jordan Davis (Board Observer)", "talk_time_sec": 15.0, "dominance_ratio": 23.8, "face_recognition_ready": True},
                {"speaker": "Akanksha Rao (Engineering Lead)", "talk_time_sec": 16.0, "dominance_ratio": 25.4, "face_recognition_ready": True},
            ],
            "active_speaker_timeline": [
                {"start": 0.0, "end": 16.0, "speaker": "Maya Chen (PMO Lead)", "source": "audio-dominance"},
                {"start": 16.0, "end": 31.0, "speaker": "Jordan Davis (Board Observer)", "source": "audio-dominance"},
                {"start": 31.0, "end": 47.0, "speaker": "Akanksha Rao (Engineering Lead)", "source": "audio-dominance"},
                {"start": 47.0, "end": 63.0, "speaker": "Maya Chen (PMO Lead)", "source": "audio-dominance"},
            ],
            "visual_identities": [],
        },
        "decision_moments": [
            {"event_id": "AI-31", "timestamp": "00:47", "speaker": "Maya Chen (PMO Lead)", "text": "Update the workflow model and export a clean follow-through pack by this evening.", "confidence": 0.91, "label": "action", "evidence": ["explicit action statement"]},
            {"event_id": "BL-31", "timestamp": "00:31", "speaker": "Akanksha Rao (Engineering Lead)", "text": "The deployment checklist still needs a final sign-off.", "confidence": 0.86, "label": "blocker", "evidence": ["final sign-off pending"]},
        ],
        "visual_artifacts": [
            {"artifact_id": "VA-31", "start_time": 6.0, "end_time": 38.0, "artifact_type": "dashboard", "confidence": 0.82, "detections": [], "display_mode": "screen-share", "content_summary": "Action register and workflow lane view.", "content_text": "Owners, deadlines, and linked decisions.", "content_insight": "The PMO sync is focused on operational follow-through rather than new decisions."},
        ],
        "workflow_model": {
            "stages": [
                {"timestamp": 0.0, "stage": "review", "speaker": "Maya Chen (PMO Lead)", "summary": "Walk current action register."},
                {"timestamp": 31.0, "stage": "blocker-check", "speaker": "Akanksha Rao (Engineering Lead)", "summary": "Review final deployment sign-off dependency."},
                {"timestamp": 47.0, "stage": "follow-through", "speaker": "Maya Chen (PMO Lead)", "summary": "Update workflow model and export pack."},
            ],
            "transitions": [{"from": "review", "to": "blocker-check", "condition": "open actions reviewed"}, {"from": "blocker-check", "to": "follow-through", "condition": "export path confirmed"}],
            "bottlenecks": ["Final deployment sign-off is still pending."],
            "prioritized_decisions": [],
            "execution_plan": [
                {"action_id": "ACT-321", "title": "Update workflow model", "owner": "Maya Chen", "due_hint": "This evening", "priority_score": 0.79, "decision_id": "", "dependencies": ["Action register latest state"], "blocker_flag": False, "status": "Ready", "notes": "Keep node descriptions board-ready."},
                {"action_id": "ACT-322", "title": "Get final deployment sign-off", "owner": "Akanksha Rao", "due_hint": "Today", "priority_score": 0.85, "decision_id": "", "dependencies": ["Checklist complete"], "blocker_flag": True, "status": "Blocked", "notes": "Required before closeout."},
            ],
            "workflow_summary": {"status": "follow-through", "top_priority_decision": "No new decision; focus is execution tracking.", "source": "boardsight-demo-seed"},
        },
        "decision_traces": [],
        "attention_sentiment": {
            "overall_attention": 74.8,
            "overall_sentiment": "neutral",
            "engagement_timeline": [{"timestamp": "00:18", "attention": 73.0}, {"timestamp": "00:50", "attention": 76.0}],
            "sentiment_timeline": [{"timestamp": "00:18", "sentiment": "focused"}, {"timestamp": "00:50", "sentiment": "operational"}],
            "cognitive_rating": {"focus": 75.0, "clarity": 79.0, "overload_risk": 29.0, "meeting_focus": 75.0, "meeting_clarity": 79.0},
            "participant_states": [],
            "model_sources": ["boardsight-demo-seed"],
            "coverage_ratio": 0.88,
        },
        "meeting_scores": {
            "impact_score": 69.0,
            "productivity_score": 77.0,
            "execution_readiness": 71.0,
            "speaker_rating": {"Maya Chen": "Operational driver"},
            "cognitive_rating": {"focus": 75.0, "clarity": 79.0, "overload_risk": 29.0, "meeting_focus": 75.0, "meeting_clarity": 79.0},
            "meeting_conclusion": "The PMO sync tightened the action register, but final deployment sign-off is still open.",
        },
        "warnings": [],
        "metadata": {"analysis_profile": "enterprise-demo", "source_mode": "recorded-import", "data_contract_version": "boardsight-demo-v1", "performance_report": {"runtime_profile": "demo-precomputed"}},
    }


def _build_primary_workflow_editor() -> dict[str, Any]:
    return {
        "meetingId": "featured-demo",
        "title": "Launch Governance Workflow",
        "nodes": [
            {
                "id": "node-1",
                "type": "start",
                "title": "Board framing",
                "owner": "Kashmira Patil",
                "status": "Completed",
                "summary": "Frame the launch decision, risk appetite, and expected follow-through standard.",
                "description": "Set the governance context before the team discusses tactical blockers.",
                "notes": "Board wants explicit ownership and escalation thresholds.",
                "handoffNotes": "Move into PMO readiness review once the decision frame is clear.",
                "acceptanceCriteria": "Launch objective, risk context, and board expectation stated on record.",
                "decisionId": "DEC-101",
                "traceId": "TRACE-301",
                "sourceStage": "frame",
                "dueDate": "2026-07-16",
                "priority": "High",
            },
            {
                "id": "node-2",
                "type": "review",
                "title": "Readiness review",
                "owner": "Maya Chen",
                "status": "In progress",
                "summary": "Review the launch dashboard, blockers, and owners.",
                "description": "Translate the meeting discussion into a clean operating view with current owners and dates.",
                "notes": "The dashboard is the main evidence artifact for the board packet.",
                "handoffNotes": "Escalate any unresolved red blockers to the decision lane.",
                "acceptanceCriteria": "Every open blocker has a named owner and due date.",
                "decisionId": "DEC-102",
                "traceId": "TRACE-302",
                "sourceStage": "review",
                "dueDate": "2026-07-17",
                "priority": "High",
            },
            {
                "id": "node-3",
                "type": "escalation",
                "title": "Risk trigger watch",
                "owner": "Jordan Davis",
                "status": "Ready",
                "summary": "Monitor the API cutoff and escalate if the risk condition trips.",
                "description": "This node exists to make the escalation rule editable and visible to operators, not just buried in the transcript.",
                "notes": "If the engineering merge misses 3 PM, the risk committee note must go out the same day.",
                "handoffNotes": "Hand off to CEO once the final risk signal is confirmed.",
                "acceptanceCriteria": "Cutoff time, trigger owner, and outbound escalation note are prepared.",
                "decisionId": "DEC-103",
                "traceId": "TRACE-303",
                "sourceStage": "decision",
                "dueDate": "2026-07-17",
                "priority": "Critical",
            },
            {
                "id": "node-4",
                "type": "decision",
                "title": "Board packet closeout",
                "owner": "Kashmira Patil",
                "status": "Queued",
                "summary": "Capture rationale, reports, and GitLab-linked actions for distribution.",
                "description": "This node keeps the export/reporting step visible so the workflow is editable rather than implicit.",
                "notes": "Attach BoardSight PDF, DOCX, and XLSX exports.",
                "handoffNotes": "Distribute to board observers after PMO confirms the final tracker.",
                "acceptanceCriteria": "Decision register, action register, and rationale section are complete.",
                "decisionId": "DEC-101",
                "traceId": "TRACE-301",
                "sourceStage": "follow-through",
                "dueDate": "2026-07-17",
                "priority": "Medium",
            },
        ],
        "links": [
            {"from": "node-1", "to": "node-2", "label": "ready to review"},
            {"from": "node-2", "to": "node-3", "label": "if blocker unresolved"},
            {"from": "node-2", "to": "node-4", "label": "if dashboard clean"},
            {"from": "node-3", "to": "node-4", "label": "after escalation watch"},
        ],
        "meta": {
            "derivedFrom": "BoardSight demo workflow seed",
            "status": "editable-demo",
            "overview": "An editable workflow that turns a board launch decision into accountable execution steps.",
            "notes": "Use this during demos to show node-level descriptions, acceptance criteria, and handoff notes.",
            "savedAt": "2026-07-16T17:45:00Z",
        },
    }
