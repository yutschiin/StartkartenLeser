"""Atomic private image copies with opaque references and idempotent cleanup."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from PIL import Image

from startkartenleser.infrastructure.image_pipeline import (
    ImageInputError,
    ImagePolicy,
    load_selected_image,
)


_IMAGE_REFERENCE = re.compile(r"[0-9a-f]{32}\.(?:jpg|png)\Z")
_TEMPORARY_REFERENCE = re.compile(r"\.[0-9a-f]{32}\.tmp\Z")


class ManagedImageStore:
    def __init__(self, directory: Path | str, policy: ImagePolicy = ImagePolicy()) -> None:
        self.directory = Path(directory)
        self.policy = policy
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.directory.chmod(0o700)
        except OSError:
            pass

    def store_selected(self, source_path: str) -> str:
        """Validate then atomically copy original bytes under an opaque name."""
        source = Path(source_path)
        loaded = load_selected_image(source, self.policy)
        extension = ".png" if loaded.format == "PNG" else ".jpg"
        identifier = uuid4().hex
        temporary = self.directory / f".{identifier}.tmp"
        destination = self.directory / f"{identifier}{extension}"
        try:
            with source.open("rb") as source_stream, temporary.open("xb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            copied = load_selected_image(temporary, self.policy)
            if copied.format != loaded.format:
                raise ImageInputError("error.image_unreadable")
            os.replace(temporary, destination)
            self._fsync_directory()
            return destination.name
        except ImageInputError:
            temporary.unlink(missing_ok=True)
            raise
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ImageInputError("error.image_copy_failed") from error

    def read_image(self, image_reference: str) -> Image.Image:
        path = self._resolve(image_reference)
        try:
            return load_selected_image(path, self.policy).image
        except ImageInputError:
            raise

    def delete_image(self, image_reference: str) -> None:
        self._resolve(image_reference).unlink(missing_ok=True)
        self._fsync_directory()

    def list_image_references(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                path.name
                for path in self.directory.iterdir()
                if path.is_file() and _IMAGE_REFERENCE.fullmatch(path.name)
            )
        )

    def cleanup_temporary_files(self) -> None:
        for path in self.directory.iterdir():
            if path.is_file() and _TEMPORARY_REFERENCE.fullmatch(path.name):
                path.unlink(missing_ok=True)
        self._fsync_directory()

    def _resolve(self, image_reference: str) -> Path:
        if not _IMAGE_REFERENCE.fullmatch(image_reference):
            raise ValueError("invalid managed-image reference")
        return self.directory / image_reference

    def _fsync_directory(self) -> None:
        try:
            descriptor = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)
