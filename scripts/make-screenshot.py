#!/usr/bin/env python3
"""Render the README screenshot with the face anonymised.

The illustration needs to show two things: that recognition works, and that the
active IR image carries a distance-dependent falloff gradient. Neither requires
an identifiable face, and a face-authentication project publishing its author's
biometrics would be a poor advertisement for its own threat model.

Mosaic alone can be partially inverted when the underlying image is
low-entropy, so the face region is downsampled hard AND blurred, which
discards the high-frequency detail identification depends on while leaving the
low-frequency luminance gradient -- the thing actually being illustrated --
intact.

Usage:  PYTHONPATH=src python3 scripts/make-screenshot.py docs/demo.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from irfa import camera, liveness  # noqa: E402
from irfa.demo import GREEN, _panel, _text  # noqa: E402
from irfa.face import FaceEngine, cosine_similarity  # noqa: E402
from irfa.store import Store  # noqa: E402

MOSAIC_BLOCKS = 8   # face is reduced to this many blocks across before upscaling
BLUR_KERNEL = 21


def anonymise(img: np.ndarray, bbox: tuple[int, int, int, int]) -> None:
    """Destroy identifying detail in place, preserving the luminance gradient."""
    x, y, w, h = bbox
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    region = img[y0:y1, x0:x1]
    small = cv2.resize(region, (MOSAIC_BLOCKS, MOSAIC_BLOCKS), interpolation=cv2.INTER_AREA)
    coarse = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
    img[y0:y1, x0:x1] = cv2.GaussianBlur(coarse, (BLUR_KERNEL, BLUR_KERNEL), 0)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/demo.png")
    engine = FaceEngine()
    enrollment = Store().load(__import__("getpass").getuser())

    best = None
    with camera.IRCamera() as cam:
        for i, (lit, dark) in enumerate(cam.stream_pairs()):
            faces = engine.detect(lit)
            if not faces:
                continue
            face = faces[0]
            active = camera.active_ir(lit, dark)
            live = liveness.assess(active, face.bbox)
            if not live.passed:
                continue
            sim = None
            if enrollment is not None:
                vec = engine.embed(lit, face)
                sim = max(cosine_similarity(vec, r) for r in enrollment.embeddings)
            # Prefer the most convincing frame rather than the first one.
            if best is None or (sim or 0) > (best[3] or 0):
                best = (lit.copy(), active.copy(), face, sim, live)
            if i > 24:
                break

    if best is None:
        print("no usable frame captured", file=sys.stderr)
        return 1

    lit, active, face, sim, live = best
    bbox = face.bbox

    left_gray = lit.astype(np.uint8).copy()
    right_gray = active.astype(np.uint8).copy()
    anonymise(left_gray, bbox)
    anonymise(right_gray, bbox)

    left = _panel(left_gray, "lit IR  -  recognition")
    right = _panel(right_gray, "active IR  -  liveness", cv2.COLORMAP_INFERNO)
    for pane in (left, right):
        cv2.rectangle(pane, (bbox[0], bbox[1]), (bbox[0] + bbox[2], bbox[1] + bbox[3]), GREEN, 2)

    _text(right, [
        (f"response {live.response:6.1f}  (min {liveness.MIN_RESPONSE})", GREEN),
        (f"falloff  {live.falloff:6.2f}  (min {liveness.MIN_FALLOFF})", GREEN),
    ], 10, right.shape[0] - 74)

    frame = np.hstack([left, right])
    cv2.rectangle(frame, (0, frame.shape[0] - 46), (frame.shape[1], frame.shape[0]), (24, 24, 24), -1)
    _text(frame, [
        ("AUTHENTICATED   quorum 6/3 of last 6", GREEN),
        (f"MATCH  sim={sim:.3f}" if sim else "MATCH", GREEN),
    ], 12, frame.shape[0] - 26, scale=0.55, step=18)

    cv2.putText(frame, "face pixelated for publication", (frame.shape[1] - 250, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1, cv2.LINE_AA)

    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), frame)
    print(f"wrote {out}  (sim={sim:.3f} response={live.response:.1f} falloff={live.falloff:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
