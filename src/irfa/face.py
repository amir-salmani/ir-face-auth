"""Face detection and embedding.

Deliberately built on the detectors bundled with OpenCV >= 4.5 (YuNet for
detection, SFace for recognition) rather than dlib. dlib is the reason Howdy
ossified: it needs a C++ toolchain at install time and its Python bindings lag
interpreter releases, which is how a face-auth package ends up unbuildable on a
current distro. YuNet and SFace ship as ONNX blobs run by OpenCV's own DNN
module, so the only runtime dependency is OpenCV itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

def _find_model_dir() -> Path:
    """Locate models across both the dev checkout and the installed layout.

    Dev:       <repo>/src/irfa/face.py  -> <repo>/models
    Installed: /usr/local/lib/irfa/irfa/face.py -> /usr/local/lib/irfa/models

    An explicit IRFA_MODEL_DIR wins, but is not relied on: pam_exec provides a
    near-empty environment, so the installed path must resolve without it.
    """
    override = os.environ.get("IRFA_MODEL_DIR")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in (here.parents[1], here.parents[2]):
        candidate = parent / "models"
        if candidate.is_dir():
            return candidate
    return here.parents[2] / "models"


MODEL_DIR = _find_model_dir()
DETECTOR_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

# YuNet was trained on visible-light faces. IR faces are lower contrast and
# lack colour cues, so a detection threshold tuned for RGB rejects them; this
# value was chosen empirically against real IR captures from this sensor.
DETECT_SCORE_THRESHOLD = 0.55


class FaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Face:
    """A detected face. `row` is YuNet's raw 15-value output, which SFace needs
    verbatim for landmark-based alignment."""

    row: np.ndarray

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        x, y, w, h = self.row[:4]
        return int(x), int(y), int(w), int(h)

    @property
    def score(self) -> float:
        return float(self.row[14])


class FaceEngine:
    def __init__(self) -> None:
        for model in (DETECTOR_MODEL, RECOGNIZER_MODEL):
            if not model.exists():
                raise FaceError(f"Missing model file: {model}")
        self._detector = cv2.FaceDetectorYN.create(
            str(DETECTOR_MODEL), "", (320, 320), DETECT_SCORE_THRESHOLD, 0.3, 5000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(RECOGNIZER_MODEL), "")

    @staticmethod
    def _to_bgr(gray: np.ndarray) -> np.ndarray:
        """Both models expect 3-channel input; replicate the IR channel."""
        if gray.ndim == 3:
            return gray
        return cv2.cvtColor(gray.astype(np.uint8), cv2.COLOR_GRAY2BGR)

    def detect(self, gray: np.ndarray) -> list[Face]:
        img = self._to_bgr(gray)
        h, w = img.shape[:2]
        self._detector.setInputSize((w, h))
        _, raw = self._detector.detect(img)
        if raw is None:
            return []
        faces = [Face(row) for row in raw]
        # Largest face wins: the enrolling user is the one closest to the
        # sensor, and the IR emitter's falloff means bystanders are dim anyway.
        faces.sort(key=lambda f: f.bbox[2] * f.bbox[3], reverse=True)
        return faces

    def embed(self, gray: np.ndarray, face: Face) -> np.ndarray:
        img = self._to_bgr(gray)
        aligned = self._recognizer.alignCrop(img, face.row)
        feature = self._recognizer.feature(aligned)
        # Normalise so comparison is a plain dot product and stored vectors are
        # scale-independent across captures.
        vec = np.asarray(feature, dtype=np.float32).ravel()
        norm = np.linalg.norm(vec)
        if norm == 0:
            raise FaceError("Degenerate (zero-norm) face embedding")
        return vec / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
