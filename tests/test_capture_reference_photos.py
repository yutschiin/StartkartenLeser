from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from PIL import Image
import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "capture_reference_photos.py"
SPEC = importlib.util.spec_from_file_location("capture_reference_photos", SCRIPT)
capture_photos = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(capture_photos)


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(output, format="JPEG")
    return output.getvalue()


def _rows() -> list[dict[str, str]]:
    return [
        {"card_no": "01", "name": "Müller", "first_name": "Anna", "image_filename": "karte-01.jpg"},
        {"card_no": "02", "name": "Schneider", "first_name": "Lukas", "image_filename": "karte-02.jpg"},
    ]


def test_reference_dataset_is_kept_in_csv_order() -> None:
    rows = capture_photos.load_dataset(capture_photos.DEFAULT_REFERENCES)

    assert len(rows) == 16
    assert [row["card_no"] for row in rows] == [f"{index:02d}" for index in range(1, 17)]
    assert rows[0]["image_filename"] == "karte-01-mueller-anna.jpg"
    assert rows[-1]["image_filename"] == "karte-16-braun-oskar.jpg"


def test_capture_saves_dataset_names_sequentially_without_overwriting(tmp_path: Path) -> None:
    output_dir = tmp_path / "new-photos"
    capture = capture_photos.DatasetCapture(_rows(), output_dir)

    with pytest.raises(capture_photos.CaptureError, match="out of dataset order"):
        capture.save_current("02", _jpeg(), "image/jpeg")
    assert not output_dir.exists()

    first = capture.save_current("01", _jpeg(), "image/jpeg")
    assert first["captured"] == 1
    assert first["current"]["card_no"] == "02"
    assert (output_dir / "karte-01.jpg").is_file()

    complete = capture.save_current("02", _jpeg(), "image/jpeg")
    assert complete["complete"] is True
    assert (output_dir / "karte-02.jpg").is_file()
    with pytest.raises(capture_photos.CaptureError, match="already been captured"):
        capture.save_current("02", _jpeg(), "image/jpeg")


def test_capture_rejects_existing_output_directory_and_bad_images(tmp_path: Path) -> None:
    existing = tmp_path / "already-here"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        capture_photos.DatasetCapture(_rows(), existing)

    capture = capture_photos.DatasetCapture(_rows(), tmp_path / "fresh")
    with pytest.raises(capture_photos.CaptureError, match="could not be decoded"):
        capture.save_current("01", b"not an image", "image/jpeg")
    assert not (tmp_path / "fresh").exists()


def test_capture_can_resume_only_a_valid_dataset_prefix(tmp_path: Path) -> None:
    output_dir = tmp_path / "partial"
    output_dir.mkdir()
    (output_dir / "karte-01.jpg").write_bytes(_jpeg())

    capture = capture_photos.DatasetCapture(_rows(), output_dir, resume=True)

    assert capture.state()["captured"] == 1
    assert capture.state()["current"]["card_no"] == "02"
    capture.save_current("02", _jpeg(), "image/jpeg")
    assert capture.state()["complete"] is True

    (output_dir / "unmapped.jpg").write_bytes(_jpeg())
    with pytest.raises(ValueError, match="complete prefix"):
        capture_photos.DatasetCapture(_rows(), output_dir, resume=True)
