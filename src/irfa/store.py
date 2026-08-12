"""Enrollment storage.

Threat note: these embeddings are an authentication credential. Anyone who can
write this file can enrol their own face as you. In the prototype they live
under the user's own data directory, which is fine for development but NOT for
a PAM deployment -- there, the store must be root-owned 0600 under /var/lib and
the comparison must happen in the privileged process, never in the camera
worker. See docs/threat-model.md.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def default_store_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "irfa"


@dataclass
class Enrollment:
    username: str
    embeddings: np.ndarray  # (n, 128) float32, L2-normalised
    meta: dict

    @property
    def count(self) -> int:
        return int(self.embeddings.shape[0])


class Store:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or default_store_dir()

    def _path(self, username: str) -> Path:
        # Usernames come from the caller, not the shell; keep them from
        # escaping the store directory regardless.
        safe = username.replace("/", "_").replace("..", "_")
        return self.dir / f"{safe}.npz"

    def save(self, enrollment: Enrollment) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(enrollment.username)
        np.savez(
            path,
            embeddings=enrollment.embeddings.astype(np.float32),
            meta=json.dumps(enrollment.meta),
        )
        os.chmod(path, 0o600)
        return path

    def load(self, username: str) -> Enrollment | None:
        path = self._path(username)
        if not path.exists():
            return None
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data["meta"]))
            return Enrollment(username, data["embeddings"], meta)

    def delete(self, username: str) -> bool:
        path = self._path(username)
        if path.exists():
            path.unlink()
            return True
        return False
