"""Labelled metric collection and threshold derivation.

Thresholds picked by hand are guesses. This module records the liveness metrics
and match scores of labelled sessions -- a live face, a phone replay, a printed
photo, a different person -- and then derives thresholds from the measured
separation between them.

The point is that every security claim this project makes should be traceable
to a session recorded here, rather than to an author's intuition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CALIB_DIR = Path(__file__).resolve().parents[2] / "calibration"

# Fraction of genuine samples we are willing to reject in exchange for a wider
# margin against attacks. 0.02 keeps the false-reject rate low while ignoring
# the occasional badly-posed frame.
GENUINE_QUANTILE = 0.02


@dataclass
class Session:
    label: str
    response: list[float] = field(default_factory=list)
    falloff: list[float] = field(default_factory=list)
    similarity: list[float] = field(default_factory=list)
    note: str = ""

    def to_json(self) -> dict:
        return {
            "label": self.label,
            "note": self.note,
            "response": self.response,
            "falloff": self.falloff,
            "similarity": self.similarity,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Session":
        return cls(
            label=data["label"],
            response=data.get("response", []),
            falloff=data.get("falloff", []),
            similarity=data.get("similarity", []),
            note=data.get("note", ""),
        )

    @property
    def count(self) -> int:
        return len(self.response)


def save(session: Session, directory: Path | None = None) -> Path:
    directory = directory or CALIB_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session.label}.json"
    path.write_text(json.dumps(session.to_json(), indent=2))
    return path


def load_all(directory: Path | None = None) -> dict[str, Session]:
    directory = directory or CALIB_DIR
    if not directory.exists():
        return {}
    out = {}
    for path in sorted(directory.glob("*.json")):
        try:
            session = Session.from_json(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            continue
        out[session.label] = session
    return out


def _stats(values: list[float]) -> str:
    if not values:
        return "no samples"
    a = np.asarray(values, dtype=float)
    return (
        f"n={a.size:3d}  min={a.min():7.2f}  p02={np.quantile(a, 0.02):7.2f}  "
        f"median={np.median(a):7.2f}  p98={np.quantile(a, 0.98):7.2f}  max={a.max():7.2f}"
    )


def report(sessions: dict[str, Session]) -> str:
    """Human-readable comparison, plus derived thresholds where possible."""
    lines: list[str] = []
    if not sessions:
        return "No calibration sessions recorded yet. Run: irfa collect --label live"

    for name in ("response", "falloff", "similarity"):
        lines.append(f"\n{name}")
        for label, session in sessions.items():
            lines.append(f"  {label:16s} {_stats(getattr(session, name))}")

    live = sessions.get("live")
    if live is None or live.count == 0:
        lines.append("\nNo 'live' session recorded, so no thresholds can be derived.")
        return "\n".join(lines)

    attacks = {k: v for k, v in sessions.items() if k != "live" and v.count}
    lines.append("\n" + "-" * 68)
    lines.append("derived thresholds")

    for metric, floor_name in (("response", "MIN_RESPONSE"), ("falloff", "MIN_FALLOFF")):
        genuine = np.asarray(getattr(live, metric), dtype=float)
        if genuine.size == 0:
            continue
        genuine_floor = float(np.quantile(genuine, GENUINE_QUANTILE))
        attack_ceiling = max(
            (float(np.max(getattr(s, metric))) for s in attacks.values() if getattr(s, metric)),
            default=None,
        )

        if attack_ceiling is None:
            lines.append(
                f"  {floor_name:13s} >= {genuine_floor:6.2f}  "
                f"(from live p{int(GENUINE_QUANTILE*100)} only -- NO ATTACK DATA, "
                f"this bounds false rejects, not false accepts)"
            )
            continue

        if attack_ceiling < genuine_floor:
            # Clean separation: sit in the middle of the gap.
            suggested = (attack_ceiling + genuine_floor) / 2
            lines.append(
                f"  {floor_name:13s} >= {suggested:6.2f}  "
                f"(attacks top out at {attack_ceiling:.2f}, genuine p"
                f"{int(GENUINE_QUANTILE*100)} is {genuine_floor:.2f}; "
                f"margin {genuine_floor - attack_ceiling:.2f})"
            )
        else:
            lines.append(
                f"  {floor_name:13s} OVERLAP -- attacks reach {attack_ceiling:.2f} but "
                f"genuine p{int(GENUINE_QUANTILE*100)} is only {genuine_floor:.2f}. "
                f"This metric cannot separate them on its own."
            )

    return "\n".join(lines)
