"""Presentation-attack detection using the emitter's strobe.

The sensor alternates emitter-on and ambient-only frames, so `active_ir`
(lit - dark) isolates light this laptop's own emitter put onto the subject and
got back. Two independent properties of that image are hard to fake:

  response  Emissive displays (phone, laptop, tablet) put out essentially
            nothing at 850nm and contribute equally to both strobe phases, so
            they cancel to near zero. A replay attack fails here.

  falloff   Active IR obeys an inverse-square law, so a real 3D face returns
            markedly more light from the nose and forehead than from the
            cheeks and jaw at the frame edge. A flat printed photo returns a
            near-uniform response. A print attack fails here.

Neither is unbeatable on its own -- a shaped IR-reflective mask defeats both --
and this module makes no claim to defeat a determined, funded attacker. It
raises the cost from "hold up a phone" to "fabricate a 3D IR-accurate mask",
which is the honest bar for consumer face auth.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

# Calibrate with `irfa calibrate` on your own hardware before trusting these.
# Defaults are deliberately conservative: they reject more than they admit.
MIN_RESPONSE = 12.0
MIN_FALLOFF = 1.25


@dataclass
class LivenessResult:
    response: float
    falloff: float
    passed: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def _region_means(active: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    """Mean active-IR return of the face's central core vs its outer ring."""
    x, y, w, h = bbox
    H, W = active.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return 0.0, 0.0

    face = active[y0:y1, x0:x1]
    fh, fw = face.shape[:2]
    # Central 40% box: nose, inner cheeks, brow -- the parts nearest the emitter.
    cy0, cy1 = int(fh * 0.30), int(fh * 0.70)
    cx0, cx1 = int(fw * 0.30), int(fw * 0.70)
    core = face[cy0:cy1, cx0:cx1]
    if core.size == 0:
        return 0.0, 0.0

    mask = np.ones(face.shape[:2], dtype=bool)
    mask[cy0:cy1, cx0:cx1] = False
    ring = face[mask]
    if ring.size == 0:
        return float(core.mean()), 0.0
    return float(core.mean()), float(ring.mean())


def assess(active: np.ndarray, bbox: tuple[int, int, int, int]) -> LivenessResult:
    core, ring = _region_means(active, bbox)
    response = core
    # Guard the divisor: a pitch-black ring would otherwise yield an infinite
    # falloff and turn a zero-signal frame into a spurious "live" verdict.
    falloff = core / max(ring, 1.0)

    if response < MIN_RESPONSE:
        return LivenessResult(
            response, falloff, False,
            f"no active IR return ({response:.1f} < {MIN_RESPONSE}); "
            f"consistent with a display replay or an out-of-range subject",
        )
    if falloff < MIN_FALLOFF:
        return LivenessResult(
            response, falloff, False,
            f"flat IR response ({falloff:.2f} < {MIN_FALLOFF}); "
            f"consistent with a printed photo rather than a 3D face",
        )
    return LivenessResult(response, falloff, True, "live 3D subject under active IR")
