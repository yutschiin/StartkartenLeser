"""Private application data paths for the current desktop platform."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class AppDataPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "startkartenleser.sqlite3"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @classmethod
    def default(cls) -> "AppDataPaths":
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
        return cls(base / "startkartenleser")

    def ensure(self) -> None:
        self.images.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.root.chmod(0o700)
            self.images.chmod(0o700)
        except OSError:
            # Some filesystems do not support POSIX permission bits.
            pass
