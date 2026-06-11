from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from boardsight_ai.config import AppConfig
from boardsight_ai.models import VisualArtifact
from boardsight_ai.providers.runtime import optional_import
from boardsight_ai.providers.vision import detect_chart_like_objects, safe_open_video, yolo_capabilities


ARTIFACT_LABELS = [
    "presentation slide",
    "dashboard",
    "chart or graph",
    "document",
    "speaker camera grid",
    "speaker close up",
    "hybrid speaker and presentation",
]

DISPLAY_LABELS = [
    "screen share",
    "speaker video",
    "hybrid meeting view",
]

PRESENTATION_KEYWORDS = ("presentation", "slide", "dashboard", "chart", "graph", "document", "screen")


@lru_cache(maxsize=2)
def _image_classifier(model_name: str):
    transformers = optional_import("transformers")
    if transformers is None:
        return None
    try:
        return transformers.pipeline("zero-shot-image-classification", model=model_name)
    except Exception:
        return None


def _to_pil_image(frame, cv2):
    pil = optional_import("PIL.Image")
    if pil is None:
        return None
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return pil.fromarray(rgb)


def _top_label(classifier, image, labels: list[str]) -> tuple[str, float] | None:
    try:
        output = classifier(image, candidate_labels=labels)
    except Exception:
        return None
    if not output:
        return None
    top = output[0]
    return str(top["label"]), float(top["score"])


def _normalize_artifact(label: str) -> str:
    return label.replace(" ", "-").replace("or-", "").strip("-")


@lru_cache(maxsize=1)
def _image_captioner():
    transformers = optional_import("transformers")
    torch = optional_import("torch")
    if transformers is None:
        return None
    try:
        model = "Salesforce/blip-image-captioning-base"
        captioner = transformers.pipeline("image-to-text", model=model)
        device = "cpu"
        if torch is not None and getattr(torch.cuda, "is_available", lambda: False)():
            device = "cuda"
        return captioner, model, device
    except Exception:
        return None


@lru_cache(maxsize=1)
def _ocr_components():
    transformers = optional_import("transformers")
    torch = optional_import("torch")
    if transformers is None:
        return None
    try:
        processor = transformers.TrOCRProcessor.from_pretrained("microsoft/trocr-small-printed")
        model = transformers.VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-small-printed")
        device = "cpu"
        if torch is not None and getattr(torch.cuda, "is_available", lambda: False)():
            device = "cuda"
            model = model.to(device)
        return processor, model, torch, device
    except Exception:
        return None


def _should_extract_content(artifact_label: str, display_label: str) -> bool:
    haystack = f"{artifact_label} {display_label}".lower()
    return any(keyword in haystack for keyword in PRESENTATION_KEYWORDS)


def _ocr_crops(frame, cv2):
    height, width = frame.shape[:2]
    regions = [
        frame,
        frame[: max(1, height // 2), :],
        frame[max(0, int(height * 0.15)): max(1, int(height * 0.75)), max(0, int(width * 0.05)): max(1, int(width * 0.95))],
    ]
    pil = optional_import("PIL.Image")
    if pil is None:
        return []
    images = []
    for region in regions:
        if region is None or region.size == 0:
            continue
        resized = cv2.resize(region, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        images.append(pil.fromarray(rgb))
    return images


def _normalize_ocr_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    cleaned = cleaned.replace("|", "I")
    return cleaned.strip()


def _normalize_caption_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    if cleaned.lower().startswith("a "):
        cleaned = cleaned[2:]
    return cleaned[:220].strip()


def _extract_content_text(frame, cv2) -> str:
    components = _ocr_components()
    if components is None:
        return ""
    processor, model, torch, device = components
    collected: list[str] = []
    try:
        for image in _ocr_crops(frame, cv2):
            pixel_values = processor(images=image, return_tensors="pt").pixel_values
            if torch is not None and device != "cpu":
                pixel_values = pixel_values.to(device)
            generated_ids = model.generate(pixel_values, max_new_tokens=64)
            text = _normalize_ocr_text(processor.batch_decode(generated_ids, skip_special_tokens=True)[0])
            if len(text) < 6:
                continue
            if any(text.lower() in existing.lower() or existing.lower() in text.lower() for existing in collected):
                continue
            collected.append(text)
            if len(collected) >= 2:
                break
    except Exception:
        return ""
    return " | ".join(collected[:2])


def _extract_visual_caption(image) -> tuple[str, str]:
    components = _image_captioner()
    if components is None:
        return "", ""
    captioner, model_name, _device = components
    try:
        output = captioner(image, max_new_tokens=48)
    except Exception:
        return "", ""
    if not output:
        return "", ""
    text = _normalize_caption_text(output[0].get("generated_text", ""))
    return text, model_name if text else ""


def _build_content_insight(
    artifact_label: str,
    display_label: str,
    content_text: str,
    visual_caption: str,
    detections: list[dict[str, Any]],
) -> str:
    evidence: list[str] = []
    if content_text:
        evidence.append(f"Slide text suggests: {content_text}")
    if visual_caption:
        evidence.append(f"Visual model view: {visual_caption}")
    detection_labels = [str(item.get("label", "")).strip() for item in detections if item.get("label")]
    if detection_labels:
        evidence.append(f"Detected elements: {', '.join(detection_labels[:4])}")
    if not evidence:
        return f"Presentation-like frame detected as {artifact_label} in {display_label} mode, but content detail was not recoverable."
    return " ".join(evidence[:3])


def _build_content_summary(
    config: AppConfig,
    display_label: str,
    display_score: float,
    detections: list[dict],
    content_text: str,
    visual_caption: str,
) -> str:
    source_parts = [
        f"zero-shot-image-classifier:{config.image_classifier_model}",
        f"display:{display_label}:{display_score:.3f}",
    ]
    if yolo_capabilities()["ultralytics"]:
        source_parts.append("object-detector:yolo")
    if detections:
        source_parts.append("objects:" + ",".join(str(item.get("label", "")) for item in detections if item.get("label")))
    if content_text:
        source_parts.append("content:" + content_text[:220])
    if visual_caption:
        source_parts.append("caption:" + visual_caption[:220])
    return "; ".join(source_parts)


def run(video_path: Path, config: AppConfig) -> tuple[list[VisualArtifact], list[str]]:
    warnings: list[str] = []
    classifier = _image_classifier(config.image_classifier_model)
    if classifier is None:
        return [], [f"Visual artifact detection unavailable: image classifier '{config.image_classifier_model}' is not loaded."]

    cap, cv2 = safe_open_video(video_path)
    if cap is None or cv2 is None:
        return [], ["Visual artifact detection unavailable: OpenCV could not read the video for model sampling."]

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_stride = max(1, int(fps * config.visual_sample_seconds))
    sample_indices = list(range(0, max(1, frame_count), sample_stride))[: config.max_visual_samples]
    if not sample_indices:
        sample_indices = [0]

    artifacts: list[VisualArtifact] = []
    artifact_index = 1

    for frame_index in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        if not ret:
            continue

        image = _to_pil_image(frame, cv2)
        if image is None:
            warnings.append("Visual artifact detection stopped: Pillow is required for transformer image inference.")
            break

        artifact_prediction = _top_label(classifier, image, ARTIFACT_LABELS)
        display_prediction = _top_label(classifier, image, DISPLAY_LABELS)
        if artifact_prediction is None or display_prediction is None:
            warnings.append("Visual artifact detection skipped one frame because model inference failed.")
            continue

        artifact_label, artifact_score = artifact_prediction
        display_label, display_score = display_prediction
        start_time = round(frame_index / fps, 2)
        detections = detect_chart_like_objects(frame, config.yolo_model_name)
        content_text = ""
        visual_caption = ""
        if _should_extract_content(artifact_label, display_label):
            if config.enable_visual_ocr:
                content_text = _extract_content_text(frame, cv2)
            if config.enable_visual_caption and not content_text:
                visual_caption, _ = _extract_visual_caption(image)
        content_insight = _build_content_insight(artifact_label, display_label, content_text, visual_caption, detections)
        content_summary = _build_content_summary(config, display_label, display_score, detections, content_text, visual_caption)

        artifacts.append(
            VisualArtifact(
                artifact_id=f"VA-{artifact_index}",
                start_time=start_time,
                end_time=round(start_time + 10.0, 2),
                artifact_type=_normalize_artifact(artifact_label),
                confidence=round(artifact_score, 3),
                detections=detections,
                display_mode=display_label.replace(" ", "-"),
                content_summary=content_summary,
                content_text=content_text,
                content_insight=content_insight,
            )
        )
        artifact_index += 1

    cap.release()

    if not artifacts:
        warnings.append("Visual artifact detector returned no model-backed artifacts.")
    return artifacts, warnings
