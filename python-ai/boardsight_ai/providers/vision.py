from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from boardsight_ai.config import AppConfig

from .runtime import dependency_available, optional_import


def face_capabilities() -> dict[str, bool]:
    return {
        "opencv": dependency_available("cv2"),
        "face_recognition": dependency_available("face_recognition"),
        "haar_faces": dependency_available("cv2"),
    }


def yolo_capabilities() -> dict[str, bool]:
    return {
        "opencv": dependency_available("cv2"),
        "ultralytics": dependency_available("ultralytics"),
    }


@lru_cache(maxsize=2)
def _yolo_model(model_name: str):
    ultralytics = optional_import("ultralytics")
    if ultralytics is None:
        return None
    try:
        return ultralytics.YOLO(model_name)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _haar_face_detector():
    cv2 = optional_import("cv2")
    if cv2 is None:
        return None
    try:
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(str(cascade_path))
        if detector.empty():
            return None
        return detector
    except Exception:
        return None


def detect_faces_in_frame(frame) -> list[dict[str, int]]:
    cv2 = optional_import("cv2")
    detector = _haar_face_detector()
    if cv2 is None or detector is None or frame is None:
        return []
    try:
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(
            grayscale,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(36, 36),
        )
    except Exception:
        return []

    detections: list[dict[str, int]] = []
    for x, y, width, height in faces:
        detections.append(
            {
                "x": int(x),
                "y": int(y),
                "width": int(width),
                "height": int(height),
            }
        )
    return detections


def detect_chart_like_objects(frame, model_name: str) -> list[dict]:
    model = _yolo_model(model_name)
    if model is None:
        return []

    try:
        results = model.predict(frame, verbose=False)
        detections: list[dict] = []
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                label = result.names[class_id]
                if label.lower() in {"tv", "laptop", "book", "cell phone", "monitor"}:
                    detections.append(
                        {
                            "label": label,
                            "confidence": round(float(box.conf[0]), 3),
                        }
                    )
        return detections
    except Exception:
        return []


def safe_open_video(video_path: Path):
    cv2 = optional_import("cv2")
    if cv2 is None:
        return None, None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None, cv2
    return cap, cv2


def _encode_frame_as_jpeg_base64(frame) -> str | None:
    cv2 = optional_import("cv2")
    if cv2 is None:
        return None
    try:
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    except Exception:
        return None
    if not ok:
        return None
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def _extract_text_from_gemini_payload(payload: dict[str, Any]) -> str | None:
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        text_parts = [str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("text")]
        combined = "".join(text_parts).strip()
        if combined:
            return combined
    return None


def analyze_frame_with_gemini(frame, config: AppConfig) -> dict[str, Any] | None:
    api_key = (config.gemini_api_key or "").strip()
    if config.llm_provider != "gemini" or not api_key:
        return None

    image_b64 = _encode_frame_as_jpeg_base64(frame)
    if not image_b64:
        return None

    prompt = (
        "Analyze this meeting video frame for BoardSight. "
        "Return valid JSON only with keys: artifact_type, display_mode, visible_people_count, "
        "screen_present, chart_present, document_present, textual_content, summary, confidence. "
        "artifact_type must be one of: participant-camera, presentation-slide, screen-share, dashboard, chart, document, mixed, none. "
        "display_mode must be one of: speaker-view, presentation, screen-share, mixed, none. "
        "If the frame is mainly people, use participant-camera. If a shared screen, chart, deck, or dashboard is visible, say so. "
        "visible_people_count should be an integer estimate. textual_content should be short extracted visible text when obvious, otherwise empty."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.gemini_model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_b64,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None

    text = _extract_text_from_gemini_payload(payload)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    parsed["_source"] = f"gemini-vision:{config.gemini_model}"
    return parsed


def analyze_sparse_frame(frame, config: AppConfig) -> dict[str, Any]:
    face_boxes = detect_faces_in_frame(frame)
    yolo_detections = detect_chart_like_objects(frame, config.yolo_model_name)
    gemini_result = analyze_frame_with_gemini(frame, config)

    if gemini_result is not None:
        return {
            "artifact_type": str(gemini_result.get("artifact_type") or "none"),
            "display_mode": str(gemini_result.get("display_mode") or "none"),
            "visible_people_count": int(gemini_result.get("visible_people_count") or len(face_boxes) or 0),
            "screen_present": bool(gemini_result.get("screen_present", False)),
            "chart_present": bool(gemini_result.get("chart_present", False)),
            "document_present": bool(gemini_result.get("document_present", False)),
            "textual_content": str(gemini_result.get("textual_content") or ""),
            "summary": str(gemini_result.get("summary") or ""),
            "confidence": float(gemini_result.get("confidence") or 0.78),
            "detections": face_boxes + yolo_detections,
            "source": str(gemini_result.get("_source") or "gemini-vision"),
        }

    artifact_type = "none"
    display_mode = "none"
    screen_present = bool(yolo_detections)
    chart_present = any(str(item.get("label", "")).lower() in {"tv", "monitor", "laptop"} for item in yolo_detections)
    document_present = any(str(item.get("label", "")).lower() in {"book", "cell phone"} for item in yolo_detections)

    if screen_present and face_boxes:
        artifact_type = "mixed"
        display_mode = "mixed"
    elif screen_present:
        artifact_type = "screen-share"
        display_mode = "screen-share"
    elif face_boxes:
        artifact_type = "participant-camera"
        display_mode = "speaker-view"

    return {
        "artifact_type": artifact_type,
        "display_mode": display_mode,
        "visible_people_count": len(face_boxes),
        "screen_present": screen_present,
        "chart_present": chart_present,
        "document_present": document_present,
        "textual_content": "",
        "summary": "",
        "confidence": 0.62 if artifact_type != "none" else 0.0,
        "detections": (
            [{"label": "face", "bbox": [item["x"], item["y"], item["width"], item["height"]], "confidence": 0.58} for item in face_boxes]
            + yolo_detections
        ),
        "source": "opencv+yolo-sparse",
    }
