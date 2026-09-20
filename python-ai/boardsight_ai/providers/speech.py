from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from boardsight_ai.config import AppConfig
from boardsight_ai.models import TranscriptSegment

from .diarization import diarize_audio
from .runtime import optional_import

_ASR_PIPELINE = None
_FASTER_WHISPER_ERROR = ""


@lru_cache(maxsize=2)
def _faster_whisper_model(model_name: str):
    global _FASTER_WHISPER_ERROR
    faster_whisper = optional_import("faster_whisper")
    if faster_whisper is None:
        _FASTER_WHISPER_ERROR = "faster_whisper import unavailable"
        return None
    try:
        model = faster_whisper.WhisperModel(model_name, device="cpu", compute_type="int8")
        _FASTER_WHISPER_ERROR = ""
        return model
    except Exception as exc:
        _FASTER_WHISPER_ERROR = f"{type(exc).__name__}: {exc}"
        return None


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]
    subprocess.run(command, check=True, capture_output=True)


def _transcribe_with_faster_whisper(audio_path: Path, model_name: str) -> list[TranscriptSegment]:
    model = _faster_whisper_model(model_name)
    if model is None:
        return []
    segments, _ = model.transcribe(str(audio_path), vad_filter=True, beam_size=1)

    transcript_segments: list[TranscriptSegment] = []
    for segment in segments:
        start = float(segment.start)
        end = float(segment.end)
        text = (segment.text or "").strip()
        if not text:
            continue
        transcript_segments.append(
            TranscriptSegment(
                start=start,
                end=end,
                speaker="Speaker-Unknown",
                text=text,
                confidence=0.9,
            )
        )
    return transcript_segments


def _get_transformer_asr():
    global _ASR_PIPELINE
    if _ASR_PIPELINE is not None:
        return _ASR_PIPELINE

    transformers = optional_import("transformers")
    if transformers is None:
        return None

    torch = optional_import("torch")
    device = 0 if torch is not None and getattr(torch.cuda, "is_available", lambda: False)() else -1
    model_candidates = [
        "openai/whisper-tiny.en",
        "openai/whisper-base.en",
    ]
    for model_name in model_candidates:
        try:
            _ASR_PIPELINE = transformers.pipeline(
                "automatic-speech-recognition",
                model=model_name,
                device=device,
            )
            return _ASR_PIPELINE
        except Exception:
            continue
    return None


def _apply_diarization(
    transcript_segments: list[TranscriptSegment],
    audio_path: Path,
    config: AppConfig,
) -> list[TranscriptSegment]:
    diarized_segments = diarize_audio(audio_path, config)
    if not diarized_segments:
        return transcript_segments

    remapped: list[TranscriptSegment] = []
    for segment in transcript_segments:
        matching = next(
            (
                diarized
                for diarized in diarized_segments
                if diarized["start"] <= segment.start <= diarized["end"]
                or diarized["start"] <= segment.end <= diarized["end"]
            ),
            None,
        )
        speaker = matching["speaker"] if matching is not None else segment.speaker
        remapped.append(
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                speaker=speaker,
                text=segment.text,
                confidence=segment.confidence,
            )
        )
    return remapped


def transcribe(video_path: Path, config: AppConfig) -> tuple[list[TranscriptSegment], list[str]]:
    warnings: list[str] = []
    audio_path = video_path.with_suffix(".boardsight.wav")
    transcript_segments: list[TranscriptSegment] = []

    try:
        _extract_audio(video_path, audio_path)
        transcript_segments = _transcribe_with_faster_whisper(audio_path, config.faster_whisper_model)
        if not transcript_segments:
            asr = _get_transformer_asr()
            if asr is None:
                raise RuntimeError(
                    "No ASR backend available. "
                    + (_FASTER_WHISPER_ERROR or "faster-whisper returned no transcript segments")
                )

            output = asr(str(audio_path), return_timestamps=True, chunk_length_s=30)
            chunks = output.get("chunks", []) if isinstance(output, dict) else []

            if chunks:
                last_end = 0.0
                for chunk in chunks:
                    start, end = chunk.get("timestamp", (0.0, 0.0))
                    if start is None:
                        start = last_end
                    if end is None:
                        end = start + 2.0
                    last_end = float(end)
                    text = str(chunk.get("text", "")).strip()
                    if not text:
                        continue
                    transcript_segments.append(
                        TranscriptSegment(
                            start=float(start),
                            end=float(end),
                            speaker="Speaker-Unknown",
                            text=text,
                            confidence=0.82,
                        )
                    )
            else:
                text = output.get("text", "").strip() if isinstance(output, dict) else ""
                if text:
                    transcript_segments.append(
                        TranscriptSegment(
                            start=0.0,
                            end=15.0,
                            speaker="Speaker-Unknown",
                            text=text,
                            confidence=0.65,
                        )
                    )
    except Exception as exc:
        warnings.append(
            f"ASR backend unavailable or failed ({type(exc).__name__}: {exc}); "
            "no transcript detections were generated."
        )

    if not transcript_segments:
        warnings.append("ASR returned no segments. Install/configure faster-whisper or transformers ASR.")

    if config.enable_diarization:
        transcript_segments = _apply_diarization(transcript_segments, audio_path, config)
    else:
        warnings.append("Diarization skipped for speed. Set BOARDSIGHT_ENABLE_DIARIZATION=true to enable pyannote speaker turns.")

    try:
        if audio_path.exists():
            audio_path.unlink()
    except OSError:
        pass

    return transcript_segments, warnings
