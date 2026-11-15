"""Private application data paths for the current desktop platform."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil


@dataclass(frozen=True)
class AppDataPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "startkartenleser.sqlite3"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def legacy_recognition_policy(self) -> Path:
        return self.root / "recognition-policy.json"

    def prepare_config(self, packaged_default: Path) -> Path:
        """Keep the old filename working while standardizing on config.json."""
        if self.config.exists():
            return self.config
        if self.legacy_recognition_policy.exists():
            self.legacy_recognition_policy.rename(self.config)
        else:
            shutil.copyfile(packaged_default, self.config)
        return self.config

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
