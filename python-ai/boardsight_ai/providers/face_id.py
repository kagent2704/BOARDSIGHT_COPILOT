from __future__ import annotations

from pathlib import Path

from .runtime import optional_import
from .vision import detect_faces_in_frame


def _signature_from_crop(crop, cv2) -> list[float]:
    resized = cv2.resize(crop, (24, 24))
    grayscale = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    normalized = grayscale.astype("float32") / 255.0
    return normalized.flatten().tolist()


def _signature_distance(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 1.0
    total = 0.0
    for lhs, rhs in zip(left, right):
        total += abs(lhs - rhs)
    return total / len(left)


def detect_known_faces(video_path: Path, sample_every_seconds: float = 8.0, max_samples: int = 8) -> list[dict]:
    cv2 = optional_import("cv2")
    face_recognition = optional_import("face_recognition")
    if cv2 is None:
        return []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride = max(1, int(fps * sample_every_seconds))
    identities: list[dict] = []

    if face_recognition is not None:
        known_encodings: list = []
        for frame_index in list(range(0, max(1, frame_count), stride))[:max_samples]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if not ret:
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb, model="cnn")
            encodings = face_recognition.face_encodings(rgb, locations)

            for location, encoding in zip(locations, encodings):
                matches = face_recognition.compare_faces(known_encodings, encoding, tolerance=0.52) if known_encodings else []
                try:
                    index = matches.index(True)
                    face_id = f"Face-{index + 1}"
                except ValueError:
                    known_encodings.append(encoding)
                    face_id = f"Face-{len(known_encodings)}"

                identities.append(
                    {
                        "identity_id": face_id,
                        "label": face_id,
                        "tracking_mode": "face-encoding",
                        "timestamp": round(frame_index / fps, 2),
                        "bbox": [int(value) for value in location],
                    }
                )
        cap.release()
        return identities

    known_signatures: list[list[float]] = []
    for frame_index in list(range(0, max(1, frame_count), stride))[:max_samples]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        if not ret:
            continue

        for face_box in detect_faces_in_frame(frame):
            x = int(face_box["x"])
            y = int(face_box["y"])
            width = int(face_box["width"])
            height = int(face_box["height"])
            crop = frame[y : y + height, x : x + width]
            if crop.size == 0:
                continue
            signature = _signature_from_crop(crop, cv2)
            match_index = None
            for index, known_signature in enumerate(known_signatures):
                if _signature_distance(signature, known_signature) <= 0.12:
                    match_index = index
                    break
            if match_index is None:
                known_signatures.append(signature)
                match_index = len(known_signatures) - 1
            face_id = f"Face-{match_index + 1}"
            identities.append(
                {
                    "identity_id": face_id,
                    "label": face_id,
                    "tracking_mode": "opencv-face-signature",
                    "timestamp": round(frame_index / fps, 2),
                    "bbox": [y, x + width, y + height, x],
                }
            )

    cap.release()
    return identities
