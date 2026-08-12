"""IR camera discovery and strobe-aware frame capture.

The Windows Hello style IR camera on this class of laptop pulses its 850nm
emitter at half the sensor frame rate: frames alternate emitter-on ("lit") and
ambient-only ("dark"). Naively grabbing a single frame lands on a dark frame
half the time and looks like broken hardware -- that is the single most common
misdiagnosis of these cameras on Linux.

We exploit the alternation instead: a (lit, dark) pair taken back to back gives
us an ambient-subtracted active IR image, which is what liveness.py works on.
"""

from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

# Frames to discard while sensor auto-exposure settles. Measured: brightness
# converges from ~43 to a stable ~20 within roughly the first dozen frames.
SETTLE_FRAMES = 14

# A frame is "lit" if its mean brightness is at least this multiple of the
# darkest frame seen. The absolute values vary with ambient IR, so we compare
# relatively rather than against a fixed threshold.
LIT_RATIO = 3.0


class CameraError(RuntimeError):
    pass


@dataclass(frozen=True)
class IRDevice:
    path: str
    name: str


def find_ir_device() -> IRDevice:
    """Locate the IR capture node by sysfs name, not by hardcoded index.

    Video node numbering is not stable across boots or USB re-enumeration, so
    /dev/video2 is never safe to assume. IR sensors advertise themselves in
    their v4l2 name; each sensor also exposes a metadata node alongside the
    capture node, distinguished by index 0.
    """
    candidates = []
    for sysdir in sorted(glob.glob("/sys/class/video4linux/video*")):
        try:
            with open(os.path.join(sysdir, "name")) as fh:
                name = fh.read().strip()
            with open(os.path.join(sysdir, "index")) as fh:
                index = int(fh.read().strip())
        except (OSError, ValueError):
            continue
        if index != 0:
            continue  # metadata node, not a capture node
        if "ir" not in name.lower().split():
            # Match "HP IR Camera" but not "Chicony Camera"; word-boundary match
            # avoids false hits on names merely containing the letters "ir".
            continue
        candidates.append(IRDevice(path=f"/dev/{os.path.basename(sysdir)}", name=name))

    if not candidates:
        raise CameraError(
            "No IR capture device found. Checked /sys/class/video4linux/*/name "
            "for a capture node advertising 'IR'."
        )
    return candidates[0]


class IRCamera:
    """Context manager yielding ambient-subtracted IR frame pairs."""

    def __init__(self, device: IRDevice | None = None, timeout_s: float = 6.0):
        self.device = device or find_ir_device()
        self.timeout_s = timeout_s
        self._cap: cv2.VideoCapture | None = None

    def __enter__(self) -> "IRCamera":
        index = int(self.device.path.removeprefix("/dev/video"))
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise CameraError(
                f"Could not open {self.device.path}. Another process may hold "
                f"the camera, or the user lacks membership of the 'video' group."
            )
        self._cap = cap
        self._settle()
        return self

    def __exit__(self, *exc) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _read_gray(self) -> np.ndarray:
        assert self._cap is not None
        ok, frame = self._cap.read()
        if not ok:
            raise CameraError(f"Read failed on {self.device.path}")
        # The sensor is 8-bit greyscale; V4L2 hands OpenCV a 3-channel BGR
        # replication of it, so any single channel is the true sensor data.
        return frame[:, :, 0] if frame.ndim == 3 else frame

    def _settle(self) -> None:
        for _ in range(SETTLE_FRAMES):
            self._read_gray()

    def capture_pairs(self, count: int = 4) -> list[tuple[np.ndarray, np.ndarray]]:
        """Return `count` (lit, dark) pairs of consecutive frames.

        Because the emitter alternates, any two consecutive frames form a pair;
        we only need to decide which of the two is the lit one.
        """
        pairs: list[tuple[np.ndarray, np.ndarray]] = []
        deadline = time.monotonic() + self.timeout_s

        while len(pairs) < count:
            if time.monotonic() > deadline:
                raise CameraError(
                    f"Timed out after {self.timeout_s}s collecting IR frame pairs "
                    f"(got {len(pairs)}/{count}). Emitter may not be strobing."
                )
            a = self._read_gray()
            b = self._read_gray()
            lit, dark = (a, b) if a.mean() >= b.mean() else (b, a)

            # Guard against both frames landing in the same strobe phase, which
            # would yield a meaningless all-zero difference image.
            if dark.mean() <= 0 or lit.mean() / max(dark.mean(), 1e-6) < LIT_RATIO:
                continue
            pairs.append((lit, dark))

        return pairs


    def stream_pairs(self):
        """Yield (lit, dark) pairs continuously until the caller stops.

        Same phase-detection as capture_pairs, but unbounded and without the
        collection deadline -- for interactive use where the user decides when
        to stop rather than a fixed sample count.
        """
        while True:
            a = self._read_gray()
            b = self._read_gray()
            lit, dark = (a, b) if a.mean() >= b.mean() else (b, a)
            if dark.mean() <= 0 or lit.mean() / max(dark.mean(), 1e-6) < LIT_RATIO:
                continue
            yield lit, dark


def active_ir(lit: np.ndarray, dark: np.ndarray) -> np.ndarray:
    """Ambient-subtracted active IR reflectance, as float32.

    This is the image an attacker cannot synthesise with a display: emissive
    screens contribute equally to both phases and cancel to zero.
    """
    return np.clip(lit.astype(np.float32) - dark.astype(np.float32), 0, 255)
