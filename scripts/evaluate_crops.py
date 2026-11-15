"""Create local, text-free visual reports for card alignment and ROI crops."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from startkartenleser.infrastructure.image_pipeline import load_selected_image
from startkartenleser.infrastructure.workflow_adapters import TemplateCardAligner
from startkartenleser.localization import TextCatalog


PALETTE = ("#087c78", "#b36a16", "#426ca8", "#9b4c7a")


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _write_overlay_report(
    image: Image.Image,
    attempt,
    destination: Path,
    text: TextCatalog,
) -> None:
    report = image.convert("RGB").copy()
    draw = ImageDraw.Draw(report)
    font = _font(max(14, min(32, image.width // 100)))
    line_width = max(3, image.width // 900)
    if not attempt.overlays:
        reason = attempt.result.reason_key or "error.alignment_uncertain"
        label = text.text(reason)
        bounds = draw.textbbox((0, 0), label, font=font)
        draw.rectangle((0, 0, bounds[2] + 20, bounds[3] + 20), fill="#8b3f2a")
        draw.text((10, 10), label, font=font, fill="white")
    for index, overlay in enumerate(attempt.overlays):
        color = PALETTE[index % len(PALETTE)]
        points = [(round(x), round(y)) for x, y in overlay.source_corners]
        draw.polygon(points, outline=color, width=line_width)
        label = text.text(overlay.label_key)
        bounds = draw.textbbox((0, 0), label, font=font)
        label_width = bounds[2] + 12
        label_height = bounds[3] + 8
        x = min(max(0, points[0][0]), max(0, image.width - label_width))
        y = max(0, points[0][1] - label_height)
        draw.rectangle((x, y, x + label_width, y + label_height), fill=color)
        draw.text((x + 6, y + 3), label, font=font, fill="white")
    report.save(destination, format="JPEG", quality=90, optimize=True)


def _write_crop_report(attempt, destination: Path, text: TextCatalog) -> None:
    crops = {**attempt.text_crops, **attempt.checkbox_crops}
    columns = 2
    cell_width = 700
    cell_height = 170
    rows = (len(crops) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#eef2f3")
    draw = ImageDraw.Draw(sheet)
    heading_font = _font(20)
    detail_font = _font(14)

    for index, (region_key, crop) in enumerate(crops.items()):
        column, row = index % columns, index // columns
        x0, y0 = column * cell_width, row * cell_height
        draw.rounded_rectangle(
            (x0 + 8, y0 + 8, x0 + cell_width - 8, y0 + cell_height - 8),
            radius=8,
            fill="white",
            outline="#ced9dd",
        )
        label_key = next(
            overlay.label_key
            for overlay in attempt.overlays
            if overlay.region_key == region_key
        )
        draw.text((x0 + 20, y0 + 16), text.text(label_key), font=heading_font, fill="#143b55")
        draw.text(
            (x0 + 20, y0 + 45),
            f"ROI {crop.width} × {crop.height} px",
            font=detail_font,
            fill="#647481",
        )
        thumb = crop.convert("RGB")
        thumb.thumbnail((cell_width - 50, cell_height - 75), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x0 + 20, y0 + 68))

    sheet.save(destination, format="JPEG", quality=92, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "images",
        nargs="+",
        type=Path,
        help="explicitly selected local card-image files (PNG/JPEG)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory outside the repository for annotated images and crop sheets",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text = TextCatalog.load()
    aligner = TemplateCardAligner()
    failed = False

    for path in args.images:
        try:
            image = load_selected_image(path).image
            attempt = aligner.align(image)
        except Exception as error:
            print(f"{path.name}: image could not be decoded ({type(error).__name__})")
            failed = True
            continue

        print(
            f"{path.name}: alignment={attempt.result.quality.value}, "
            f"layout={attempt.result.schema_version}, "
            f"text_crops={len(attempt.text_crops)}, "
            f"checkbox_crops={len(attempt.checkbox_crops)}, "
            f"labeled_overlays={len(attempt.overlays)}"
        )
        overlay_path = args.output_dir / f"{path.stem}-overlay.jpg"
        _write_overlay_report(image, attempt, overlay_path, text)
        print(f"  overlay report: {overlay_path}")
        if attempt.result.quality.value == "accepted" and attempt.overlays:
            crop_path = args.output_dir / f"{path.stem}-crops.jpg"
            _write_crop_report(attempt, crop_path, text)
            print(f"  crop report: {crop_path}")
        else:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
