"""Live visualisation of the authentication pipeline.

Shows both halves of the strobe side by side: the lit frame the recogniser
works on, and the ambient-subtracted active IR image the liveness check works
on. Watching them together makes the spoofing story concrete -- hold up a phone
and the left pane still shows a face while the right pane goes black.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import cv2
import numpy as np

from . import camera, liveness
from .face import FaceEngine, cosine_similarity
from .store import Store

GREEN = (80, 220, 100)
RED = (70, 70, 240)
AMBER = (60, 190, 240)
GREY = (170, 170, 170)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _panel(gray: np.ndarray, title: str, colormap: int | None = None) -> np.ndarray:
    img = gray.astype(np.uint8)
    img = cv2.applyColorMap(img, colormap) if colormap is not None else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    cv2.putText(img, title, (10, 22), FONT, 0.6, GREY, 1, cv2.LINE_AA)
    return img


def _text(img, lines, x, y0, scale=0.5, step=20):
    for i, (txt, colour) in enumerate(lines):
        cv2.putText(img, txt, (x, y0 + i * step), FONT, scale, colour, 1, cv2.LINE_AA)


def run(threshold: float, quorum: int, window: int, user: str, save_dir: Path | None, headless_frames: int) -> int:
    engine = FaceEngine()
    enrollment = Store().load(user)
    if enrollment is None:
        print(f"No enrollment for '{user}'. Run: irfa enroll")
        return 2

    recent: deque[bool] = deque(maxlen=window)
    saved = 0
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    print("Live demo. Left = lit IR (recognition). Right = active IR (liveness).")
    if not headless_frames:
        print("Keys: q quit, s save snapshot")

    with camera.IRCamera() as cam:
        for n, (lit, dark) in enumerate(cam.stream_pairs(), start=1):
            active = camera.active_ir(lit, dark)
            faces = engine.detect(lit)

            left = _panel(lit, "lit IR  -  recognition")
            right = _panel(active, "active IR  -  liveness", cv2.COLORMAP_INFERNO)

            status, colour = "no face", GREY
            if faces:
                face = faces[0]
                x, y, w, h = face.bbox
                live = liveness.assess(active, face.bbox)

                if live.passed:
                    vec = engine.embed(lit, face)
                    sim = max(cosine_similarity(vec, ref) for ref in enrollment.embeddings)
                    ok = sim >= threshold
                    recent.append(ok)
                    colour = GREEN if ok else RED
                    status = f"{'MATCH' if ok else 'no match'}  sim={sim:.3f}"
                else:
                    recent.append(False)
                    colour = AMBER
                    sim = None
                    status = f"SPOOF REJECTED  {live.reason.split(';')[0]}"

                for pane in (left, right):
                    cv2.rectangle(pane, (x, y), (x + w, y + h), colour, 2)

                _text(right, [
                    (f"response {live.response:6.1f}  (min {liveness.MIN_RESPONSE})",
                     GREEN if live.response >= liveness.MIN_RESPONSE else RED),
                    (f"falloff  {live.falloff:6.2f}  (min {liveness.MIN_FALLOFF})",
                     GREEN if live.falloff >= liveness.MIN_FALLOFF else RED),
                ], 10, right.shape[0] - 74)  # clear of the status bar painted below

            passes = sum(recent)
            decision = "AUTHENTICATED" if passes >= quorum else "DENIED"
            dec_colour = GREEN if passes >= quorum else RED

            frame = np.hstack([left, right])
            cv2.rectangle(frame, (0, frame.shape[0] - 46), (frame.shape[1], frame.shape[0]), (24, 24, 24), -1)
            _text(frame, [
                (f"{decision}   quorum {passes}/{quorum} of last {len(recent)}", dec_colour),
                (status, colour),
            ], 12, frame.shape[0] - 26, scale=0.55, step=18)

            if headless_frames:
                if save_dir and n <= headless_frames:
                    cv2.imwrite(str(save_dir / f"demo_{n:02d}.png"), frame)
                if n >= headless_frames:
                    print(f"wrote {min(n, headless_frames)} annotated frames to {save_dir}")
                    return 0
                continue

            cv2.imshow("ir-face-auth", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s") and save_dir:
                saved += 1
                cv2.imwrite(str(save_dir / f"snapshot_{saved:02d}.png"), frame)
                print(f"saved snapshot {saved}")

    cv2.destroyAllWindows()
    return 0
