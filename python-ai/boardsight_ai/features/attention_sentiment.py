from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from boardsight_ai.config import AppConfig
from boardsight_ai.models import AttentionSentimentResult, TranscriptSegment
from boardsight_ai.providers.runtime import optional_import


EMOTION_SENTIMENT_MAP = {
    "happy": "positive",
    "surprise": "positive",
    "neutral": "neutral",
    "fear": "negative",
    "sad": "negative",
    "angry": "negative",
    "disgust": "negative",
}

ATTENTION_LABELS = [
    "attentive engaged meeting participant",
    "distracted disengaged meeting participant",
    "neutral meeting participant",
]


def _speaker_at_time(timestamp: float, transcript_segments: list[TranscriptSegment]) -> str:
    for segment in transcript_segments:
        if segment.start <= timestamp <= segment.end:
            return segment.speaker
    if not transcript_segments:
        return "Unknown Speaker"
    return min(transcript_segments, key=lambda item: abs(item.start - timestamp)).speaker


def _emotion_confidence(face_analysis: dict) -> float:
    emotions = face_analysis.get("emotion", {})
    if not isinstance(emotions, dict) or not emotions:
        return 0.45
    return max(float(score) for score in emotions.values()) / 100.0


@lru_cache(maxsize=2)
def _attention_pipeline(model_name: str):
    transformers = optional_import("transformers")
    if transformers is None:
        return None
    try:
        return transformers.pipeline("zero-shot-image-classification", model=model_name)
    except Exception:
        return None


def _run_deepface(
    video_path: Path,
    transcript_segments: list[TranscriptSegment],
    config: AppConfig,
) -> AttentionSentimentResult | None:
    deepface = optional_import("deepface.DeepFace")
    if deepface is None:
        return None
    classifier = _attention_pipeline(config.image_classifier_model)
    if classifier is None:
        return None
    cv2 = optional_import("cv2")
    pil = optional_import("PIL.Image")
    if cv2 is None or pil is None:
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    sample_stride = max(1, int(fps * config.video_sample_seconds))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_indices = list(range(0, max(1, frame_count), sample_stride))[: config.max_attention_samples]
    raw_samples: list[dict] = []

    try:
        for frame_index in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if not ret:
                continue
            timestamp = round(frame_index / fps, 2)
            try:
                analysis = deepface.analyze(
                    frame,
                    actions=["emotion"],
                    enforce_detection=False,
                    detector_backend=config.deepface_detector_backend,
                    silent=True,
                )
            except Exception:
                continue

            faces = analysis if isinstance(analysis, list) else [analysis]
            faces = [item for item in faces if isinstance(item, dict)]
            if not faces:
                continue

            try:
                image = pil.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                attention_output = classifier(image, candidate_labels=ATTENTION_LABELS)
                attention_top = attention_output[0] if attention_output else {}
            except Exception:
                continue

            def area(item):
                region = item.get("region") or item.get("facial_area") or {}
                return int(region.get("w", 0) or 0) * int(region.get("h", 0) or 0)

            face = max(faces, key=area)
            region = face.get("region") or face.get("facial_area") or {}
            emotions = face.get("emotion", {})
            raw_samples.append(
                {
                    "timestamp": timestamp,
                    "dominant_emotion": str(face.get("dominant_emotion", "neutral")).lower(),
                    "emotion_scores": emotions if isinstance(emotions, dict) else {},
                    "attention_label": str(attention_top.get("label", "neutral meeting participant")),
                    "attention_score": float(attention_top.get("score", 0.0) or 0.0),
                    "region": {
                        "x": int(region.get("x", 0) or 0),
                        "y": int(region.get("y", 0) or 0),
                        "w": int(region.get("w", 0) or 0),
                        "h": int(region.get("h", 0) or 0),
                    },
                }
            )
    finally:
        cap.release()

    if not raw_samples:
        return None

    sampled_frames = len(raw_samples)
    detected_frames = len(raw_samples)
    engagement_timeline: list[dict] = []
    sentiment_timeline: list[dict] = []
    participant_rollup: dict[str, dict] = defaultdict(
        lambda: {
            "samples": 0,
            "attention_total": 0.0,
            "emotions": Counter(),
            "max_confidence": 0.0,
        }
    )

    for sample in raw_samples:
        timestamp = float(sample.get("timestamp", 0.0))
        speaker = _speaker_at_time(timestamp, transcript_segments)
        dominant_emotion = str(sample.get("dominant_emotion", "neutral")).lower()
        sentiment = EMOTION_SENTIMENT_MAP.get(dominant_emotion, "neutral")
        face_analysis = {
            "emotion": sample.get("emotion_scores", {}),
            "region": sample.get("region", {}),
        }
        confidence = round(_emotion_confidence(face_analysis), 3)
        attention_label = str(sample.get("attention_label", "neutral meeting participant"))
        attention_model_score = float(sample.get("attention_score", 0.0))
        if attention_label == "attentive engaged meeting participant":
            attention = round(attention_model_score * 100.0, 2)
        elif attention_label == "neutral meeting participant":
            attention = round(attention_model_score * 50.0, 2)
        else:
            attention = round((1.0 - attention_model_score) * 100.0, 2)

        engagement_timeline.append(
            {
                "timestamp": timestamp,
                "speaker": speaker,
                "attention_score": attention,
                "attention_label": attention_label,
                "emotion": dominant_emotion,
                "source": f"zero-shot-image-classifier:{config.image_classifier_model}",
            }
        )
        sentiment_timeline.append(
            {
                "timestamp": timestamp,
                "speaker": speaker,
                "sentiment": sentiment,
                "emotion": dominant_emotion,
                "confidence": confidence,
                "source": "deepface-emotion",
            }
        )

        participant_state = participant_rollup[speaker]
        participant_state["samples"] += 1
        participant_state["attention_total"] += attention
        participant_state["emotions"][dominant_emotion] += 1
        participant_state["max_confidence"] = max(participant_state["max_confidence"], confidence)

    overall_attention = round(
        sum(item["attention_score"] for item in engagement_timeline) / max(1, len(engagement_timeline)),
        2,
    )
    sentiment_counter = Counter(item["sentiment"] for item in sentiment_timeline)
    overall_sentiment = max(sentiment_counter, key=sentiment_counter.get)
    coverage_ratio = round(detected_frames / max(1, sampled_frames), 2)
    cognitive_rating = {
        "focus": overall_attention,
        "clarity": round(sum(item["confidence"] for item in sentiment_timeline) / max(1, len(sentiment_timeline)) * 100.0, 2),
        "overload_risk": round(100.0 - overall_attention, 2),
    }

    participant_states = []
    for speaker, stats in participant_rollup.items():
        dominant_emotion = max(stats["emotions"], key=stats["emotions"].get)
        participant_states.append(
            {
                "speaker": speaker,
                "samples": stats["samples"],
                "average_attention": round(stats["attention_total"] / max(1, stats["samples"]), 2),
                "dominant_emotion": dominant_emotion,
                "peak_confidence": round(stats["max_confidence"], 3),
            }
        )

    return AttentionSentimentResult(
        overall_attention=overall_attention,
        overall_sentiment=overall_sentiment,
        engagement_timeline=engagement_timeline,
        sentiment_timeline=sentiment_timeline,
        cognitive_rating=cognitive_rating,
        participant_states=sorted(participant_states, key=lambda item: item["average_attention"], reverse=True),
        model_sources=["deepface-emotion", f"deepface-detector:{config.deepface_detector_backend}"],
        coverage_ratio=coverage_ratio,
    )


def _unavailable_result() -> AttentionSentimentResult:
    return AttentionSentimentResult(
        overall_attention=0.0,
        overall_sentiment="unavailable",
        engagement_timeline=[],
        sentiment_timeline=[],
        cognitive_rating={"focus": 0.0, "clarity": 0.0, "overload_risk": 0.0},
        participant_states=[],
        model_sources=[],
        coverage_ratio=0.0,
    )


def run(
    transcript_segments: list[TranscriptSegment],
    config: AppConfig,
    video_path: Path | None = None,
) -> AttentionSentimentResult:
    if not config.enable_attention_analysis:
        return _unavailable_result()
    if video_path is not None:
        model_result = _run_deepface(video_path, transcript_segments, config)
        if model_result is not None:
            return model_result
    return _unavailable_result()
