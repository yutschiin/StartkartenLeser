"""Safe image intake, conservative card rectification, and versioned crops."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from startkartenleser.domain.contracts import AlignmentQuality, AlignmentResult, RegionOverlay
from startkartenleser.domain.schema import (
    CARD_LAYOUT_A6_V1,
    CARD_LAYOUT_A6_V2,
    CARD_LAYOUT_A6_V3,
    CARD_LAYOUT_A6_V4,
    CARD_LAYOUT_V1,
    CARD_LAYOUT_V2,
    REGION_LABEL_KEYS,
)


CANONICAL_SIZE = (1000, 1400)
A6_CANONICAL_SIZE = (1050, 1480)
CARD_LAYOUT_V2_VERTICAL_OFFSET = 80
MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
MAX_SOURCE_DIMENSION = 10_000
# Printed A6 geometry at 10 px/mm: 7.8 mm markers centred 8 mm from each edge.
A6_MARKER_CENTERS = {0: (80, 80), 1: (970, 80), 2: (80, 1400), 3: (970, 1400)}
A6_MARKER_SIZE = 78
IDENTITY_TRANSFORM = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
A6_MIN_MARKERS = 3
A6_MAX_MARKER_ERROR = 12.0


class ImageInputError(ValueError):
    """Image intake failed with a stable localization key."""

    def __init__(self, localization_key: str) -> None:
        super().__init__(localization_key)
        self.localization_key = localization_key


@dataclass(frozen=True)
class ImagePolicy:
    max_file_bytes: int = MAX_SOURCE_BYTES
    max_pixels: int = MAX_SOURCE_PIXELS
    max_dimension: int = MAX_SOURCE_DIMENSION
    preview_size: tuple[int, int] = (1200, 1200)


@dataclass(frozen=True)
class LoadedImage:
    image: Image.Image
    preview: Image.Image
    format: str


@dataclass(frozen=True)
class RectifiedCard:
    image: Image.Image
    result: AlignmentResult
    corners: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class FieldRegion:
    key: str
    left: int
    top: int
    right: int
    bottom: int


# Coordinates are measured against the supplied blank Startkarte and versioned
# independently from the schema so crop geometry can be evaluated/migrated.
TEXT_REGIONS = (
    FieldRegion("name", 250, 145, 890, 320),
    FieldRegion("first_name", 295, 295, 890, 440),
    FieldRegion("year", 270, 425, 470, 560),
    FieldRegion("course_position", 340, 795, 875, 925),
    FieldRegion("heat", 205, 900, 405, 1040),
    FieldRegion("lane", 570, 900, 865, 1040),
    FieldRegion("time", 340, 1000, 875, 1110),
    FieldRegion("timekeeper", 340, 1095, 875, 1290),
)
CHECKBOX_REGIONS = (
    FieldRegion("checkbox_female", 155, 565, 225, 650),
    FieldRegion("checkbox_male", 490, 565, 560, 650),
)
A6_TEXT_REGIONS = (
    FieldRegion("name", 127, 296, 924, 359),
    FieldRegion("first_name", 127, 429, 924, 493),
    FieldRegion("year", 128, 564, 366, 631),
    FieldRegion("course", 127, 696, 505, 763),
    FieldRegion("position", 548, 696, 928, 763),
    FieldRegion("heat", 127, 829, 505, 896),
    FieldRegion("lane", 560, 829, 928, 896),
    # Overlay bounds cover each printed cell group. OCR crops below concatenate
    # only the cell interiors, excluding borders and the printed min/sek labels.
    FieldRegion("time_minutes", 119, 958, 217, 1037),
    FieldRegion("time_seconds", 285, 958, 384, 1037),
    FieldRegion("time_fraction", 420, 958, 577, 1037),
    FieldRegion("timekeeper", 127, 1097, 928, 1164),
)
A6_TIME_DIGIT_CELLS = {
    "time_minutes": ((127, 967, 160, 1028), (177, 967, 210, 1028)),
    "time_seconds": ((293, 967, 326, 1028), (346, 967, 379, 1028)),
    "time_fraction": (
        (428, 967, 461, 1028),
        (481, 967, 514, 1028),
        (535, 967, 568, 1028),
    ),
}
A6_CHECKBOX_REGIONS = (
    FieldRegion("checkbox_female", 400, 572, 460, 633),
    FieldRegion("checkbox_male", 617, 572, 677, 633),
)
A6_LINE_TEXT_REGIONS = (
    FieldRegion("name", 220, 220, 935, 326),
    FieldRegion("first_name", 255, 355, 935, 460),
    FieldRegion("year", 260, 500, 505, 598),
    FieldRegion("course", 240, 765, 515, 868),
    FieldRegion("position", 625, 765, 935, 868),
    FieldRegion("heat", 205, 900, 515, 1002),
    FieldRegion("lane", 625, 900, 935, 1002),
    FieldRegion("time", 295, 1035, 935, 1138),
    FieldRegion("timekeeper", 290, 1170, 935, 1272),
)
A6_LINE_CHECKBOX_REGIONS = (
    # Use only the interiors so thick printed borders cannot count as marks.
    FieldRegion("checkbox_female", 598, 582, 621, 601),
    FieldRegion("checkbox_male", 813, 582, 836, 601),
)
A6_FORM_TEXT_REGIONS = (
    FieldRegion("name", 215, 220, 935, 282),
    FieldRegion("first_name", 250, 350, 935, 416),
    FieldRegion("year", 260, 500, 505, 590),
    FieldRegion("course", 240, 760, 515, 868),
    FieldRegion("position", 625, 760, 935, 868),
    FieldRegion("heat", 200, 880, 495, 972),
    FieldRegion("lane", 625, 880, 935, 972),
    FieldRegion("time", 290, 1015, 935, 1116),
    FieldRegion("timekeeper", 290, 1145, 935, 1240),
)
A6_FORM_CHECKBOX_REGIONS = (
    # PDF widgets are 3.8 mm squares, positioned differently from the HTML draft.
    FieldRegion("checkbox_female", 580, 562, 620, 604),
    FieldRegion("checkbox_male", 790, 562, 830, 604),
)
A6_FORM_V4_TEXT_REGIONS = (
    FieldRegion("name", 215, 220, 935, 282),
    FieldRegion("first_name", 250, 350, 935, 416),
    FieldRegion("year", 260, 500, 505, 590),
    FieldRegion("course", 240, 760, 515, 838),
    FieldRegion("position", 625, 750, 950, 838),
    # Crop the writing area above the WK-Nr. baseline, not the printed line.
    FieldRegion("wk_number", 220, 916, 385, 969),
    FieldRegion("heat", 465, 900, 650, 970),
    FieldRegion("lane", 745, 900, 935, 970),
    FieldRegion("time", 290, 1015, 935, 1106),
    FieldRegion("timekeeper", 290, 1145, 935, 1240),
)


def regions_for_layout(layout_version: str) -> tuple[FieldRegion, ...]:
    """Return crop boxes for a registered blank-card print layout."""
    if layout_version == CARD_LAYOUT_A6_V1:
        return (*A6_TEXT_REGIONS, *A6_CHECKBOX_REGIONS)
    if layout_version == CARD_LAYOUT_A6_V2:
        return (*A6_LINE_TEXT_REGIONS, *A6_LINE_CHECKBOX_REGIONS)
    if layout_version == CARD_LAYOUT_A6_V3:
        return (*A6_FORM_TEXT_REGIONS, *A6_FORM_CHECKBOX_REGIONS)
    if layout_version == CARD_LAYOUT_A6_V4:
        return (*A6_FORM_V4_TEXT_REGIONS, *A6_FORM_CHECKBOX_REGIONS)
    if layout_version == CARD_LAYOUT_V1:
        vertical_offset = 0
    elif layout_version == CARD_LAYOUT_V2:
        vertical_offset = CARD_LAYOUT_V2_VERTICAL_OFFSET
    else:
        raise ValueError(f"unsupported card layout version: {layout_version}")
    return tuple(
        FieldRegion(
            region.key,
            region.left,
            region.top + vertical_offset,
            region.right,
            region.bottom + vertical_offset,
        )
        for region in (*TEXT_REGIONS, *CHECKBOX_REGIONS)
    )


def _regions_for_image(image: Image.Image, layout_version: str) -> tuple[FieldRegion, ...]:
    """Experimentally fit V4 text boxes to the printed writing baselines."""
    regions = regions_for_layout(layout_version)
    if layout_version != CARD_LAYOUT_A6_V4:
        return regions

    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    fitted = []
    for region in regions:
        if region.key.startswith("checkbox_"):
            fitted.append(region)
            continue
        scan_top = max(0, region.bottom - 32)
        scan_bottom = min(image.height, region.bottom + 25)
        band = ink[scan_top:scan_bottom, region.left:region.right]
        row_ink = np.count_nonzero(band, axis=1)
        if not len(row_ink):
            fitted.append(region)
            continue
        line_offset = int(np.argmax(row_ink))
        minimum_line_ink = max(35, int((region.right - region.left) * 0.6))
        if int(row_ink[line_offset]) < minimum_line_ink:
            fitted.append(region)
            continue

        # Use the detected rule as the lower edge, with a small clean-paper gap.
        # Preserve the tuned field height and slide the box with the local rule.
        line_y = scan_top + line_offset
        new_bottom = line_y - 8
        height = region.bottom - region.top
        new_top = new_bottom - height
        if new_top >= 0:
            fitted.append(FieldRegion(region.key, region.left, new_top, region.right, new_bottom))
        else:
            fitted.append(region)
    return tuple(fitted)


def load_selected_image(path: Path | str, policy: ImagePolicy = ImagePolicy()) -> LoadedImage:
    """Decode only a selected PNG/JPEG after bounded file and pixel checks."""
    selected = Path(path)
    try:
        file_size = selected.stat().st_size
    except OSError as error:
        raise ImageInputError("error.image_unreadable") from error
    if file_size <= 0 or file_size > policy.max_file_bytes:
        raise ImageInputError("error.image_too_large")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(selected) as source:
                if source.format not in ("PNG", "JPEG"):
                    raise ImageInputError("error.unsupported_image")
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > policy.max_dimension
                    or height > policy.max_dimension
                    or width * height > policy.max_pixels
                ):
                    raise ImageInputError("error.image_too_large")
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGB")
                preview = oriented.copy()
                preview.thumbnail(policy.preview_size, Image.Resampling.LANCZOS)
                return LoadedImage(oriented.copy(), preview, source.format)
    except ImageInputError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ImageInputError("error.image_unreadable") from error


def detect_card_corners(image: Image.Image) -> tuple[tuple[float, float], ...] | None:
    """Find a single strong, upright portrait card quadrilateral or return None."""
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(gray.shape[0] * gray.shape[1])
    candidates: list[tuple[float, np.ndarray]] = []

    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < image_area * 0.04 or area > image_area * 0.98:
            continue
        polygon = _approximate_quad(contour)
        if polygon is not None:
            candidates.append((area, polygon))

    # A paper/card surface may have a curved or shadowed edge that Canny breaks
    # into open contours. The brightest substantial connected region provides a
    # second conservative proposal; the later aspect/angle/heading checks still
    # reject uncertain geometry.
    _, bright = cv2.threshold(blurred, 185, 255, cv2.THRESH_BINARY)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(bright)
    if component_count > 1:
        component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        component_area = int(stats[component, cv2.CC_STAT_AREA])
        if image_area * 0.04 <= component_area <= image_area * 0.95:
            component_mask = np.asarray(labels == component, dtype=np.uint8) * 255
            component_contours, _ = cv2.findContours(
                component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if component_contours:
                contour = max(component_contours, key=cv2.contourArea)
                polygon = _approximate_quad(contour)
                if polygon is not None:
                    candidates.append((float(cv2.contourArea(contour)), polygon))

    # The card stock is lightly green/cream while the table/background is
    # usually near-neutral. Completed cards can have ink/shadows that break the
    # brightness component, so use a conservative paper-hue mask as an
    # independent boundary proposal. Geometry and heading validation below
    # still decide whether the result is safe enough to accept.
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    paper_mask = cv2.inRange(
        hsv,
        np.asarray((10, 4, 50), dtype=np.uint8),
        np.asarray((85, 255, 255), dtype=np.uint8),
    )
    color_count, color_labels, color_stats, _ = cv2.connectedComponentsWithStats(paper_mask)
    if color_count > 1:
        color_component = 1 + int(np.argmax(color_stats[1:, cv2.CC_STAT_AREA]))
        color_area = int(color_stats[color_component, cv2.CC_STAT_AREA])
        if image_area * 0.04 <= color_area <= image_area * 0.95:
            color_mask = np.asarray(color_labels == color_component, dtype=np.uint8) * 255
            color_contours, _ = cv2.findContours(
                color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if color_contours:
                contour = max(color_contours, key=cv2.contourArea)
                polygon = _approximate_quad(contour)
                if polygon is not None:
                    candidates.append((float(cv2.contourArea(contour)), polygon))
    plausible: list[tuple[float, np.ndarray]] = []
    for candidate_area, points in candidates:
        ordered = _order_corners(points)
        if not _geometry_is_plausible(ordered, image_area):
            continue
        width = (_distance(ordered[0], ordered[1]) + _distance(ordered[3], ordered[2])) / 2
        height = (_distance(ordered[0], ordered[3]) + _distance(ordered[1], ordered[2])) / 2
        aspect = width / height if height else 0
        if 0.55 <= aspect <= 0.90:
            plausible.append((candidate_area, ordered))
    if not plausible:
        return None
    _, ordered = max(plausible, key=lambda candidate: candidate[0])
    return tuple((float(x), float(y)) for x, y in ordered)


def align_card(image: Image.Image) -> RectifiedCard | None:
    """Use A6 fiducials when present; otherwise try the observed legacy layouts."""
    marker_alignment = _align_a6_markers(image)
    if marker_alignment is not None:
        return marker_alignment

    corners = detect_card_corners(image)
    if corners is None:
        return None
    aligned = rectify_card(image, corners, quality=AlignmentQuality.ACCEPTED)
    layout_version = _template_layout_version(aligned.image)
    if layout_version is not None:
        result = replace(aligned.result, schema_version=layout_version)
        return RectifiedCard(aligned.image, result, aligned.corners)
    result = replace(
        aligned.result,
        quality=AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT,
        confidence=None,
        reason_key="error.alignment_orientation_uncertain",
    )
    return RectifiedCard(aligned.image, result, aligned.corners)


def rectify_card(
    image: Image.Image,
    corners: tuple[tuple[float, float], ...] | list[tuple[float, float]],
    *,
    quality: AlignmentQuality = AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT,
) -> RectifiedCard:
    """Perspective-correct user-supplied TL, TR, BR, BL points to canonical size."""
    if len(corners) != 4:
        raise ValueError("exactly four corners are required")
    source_points = np.asarray(corners, dtype=np.float32)
    if not _corners_are_valid(source_points, image.size):
        raise ValueError("corners must form a convex quadrilateral within the image")

    width, height = CANONICAL_SIZE
    target_points = np.asarray(
        ((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)),
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source_points, target_points)
    warped = cv2.warpPerspective(
        cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR),
        matrix,
        CANONICAL_SIZE,
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    result = AlignmentResult(
        quality=quality,
        transform=tuple(float(value) for value in matrix.reshape(-1)),
        confidence=1.0 if quality is AlignmentQuality.ACCEPTED else None,
        schema_version=CARD_LAYOUT_V1,
    )
    output = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
    return RectifiedCard(output, result, tuple((float(x), float(y)) for x, y in source_points))


def crop_card_regions(
    image: Image.Image,
    *,
    layout_version: str = CARD_LAYOUT_V1,
) -> dict[str, Image.Image]:
    """Crop versioned handwriting/checkbox ROIs from an aligned card image."""
    is_a6 = layout_version in (
        CARD_LAYOUT_A6_V1, CARD_LAYOUT_A6_V2, CARD_LAYOUT_A6_V3, CARD_LAYOUT_A6_V4,
    )
    expected_size = A6_CANONICAL_SIZE if is_a6 else CANONICAL_SIZE
    if image.size != expected_size:
        raise ValueError(f"aligned card must be {expected_size[0]}x{expected_size[1]}")
    crops: dict[str, Image.Image] = {}
    checkbox_keys = {region.key for region in A6_CHECKBOX_REGIONS}
    for region in _regions_for_image(image, layout_version):
        if not (0 <= region.left < region.right <= image.width):
            raise ValueError(f"invalid horizontal crop bounds for {region.key}")
        if not (0 <= region.top < region.bottom <= image.height):
            raise ValueError(f"invalid vertical crop bounds for {region.key}")
        cell_bounds = A6_TIME_DIGIT_CELLS.get(region.key) if layout_version == CARD_LAYOUT_A6_V1 else None
        if cell_bounds is not None:
            cell_crops = [image.crop(bounds) for bounds in cell_bounds]
            cell_gap = 6
            crop = Image.new(
                "RGB",
                (sum(cell.width for cell in cell_crops) + cell_gap * (len(cell_crops) - 1),
                 max(cell.height for cell in cell_crops)),
                "white",
            )
            offset_x = 0
            for cell in cell_crops:
                crop.paste(cell, (offset_x, 0))
                offset_x += cell.width + cell_gap
        else:
            crop = image.crop((region.left, region.top, region.right, region.bottom))
        if is_a6 and region.key not in checkbox_keys:
            crop = _normalize_a6_text_crop(crop)
        crops[region.key] = crop
    return crops


def crop_contains_handwriting(crop: Image.Image) -> bool:
    """Reject blank/textured ROIs before A6 OCR to avoid empty-cell hallucinations."""
    if not isinstance(crop, Image.Image) or crop.width < 8 or crop.height < 8:
        return False
    gray = np.asarray(crop.convert("L"), dtype=np.uint8)
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=3)
    ink = np.asarray(
        gray.astype(np.int16) < background.astype(np.int16) - 28,
        dtype=np.uint8,
    )
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    for component in range(1, component_count):
        area = int(stats[component, cv2.CC_STAT_AREA])
        width = int(stats[component, cv2.CC_STAT_WIDTH])
        height = int(stats[component, cv2.CC_STAT_HEIGHT])
        if area >= 8 and width >= 2 and height >= 3:
            return True
    return False


def project_region_overlays(
    transform: tuple[float, ...] | None,
    *,
    layout_version: str = CARD_LAYOUT_V1,
    aligned_image: Image.Image | None = None,
) -> tuple[RegionOverlay, ...]:
    """Project canonical crop rectangles back onto the orientation-normalized source image."""
    if transform is None or len(transform) != 9:
        return ()
    try:
        inverse = np.linalg.inv(np.asarray(transform, dtype=np.float64).reshape(3, 3))
    except np.linalg.LinAlgError:
        return ()

    overlays: list[RegionOverlay] = []
    regions = (
        _regions_for_image(aligned_image, layout_version)
        if aligned_image is not None else regions_for_layout(layout_version)
    )
    for region in regions:
        canonical = np.asarray(
            [[
                (region.left, region.top),
                (region.right, region.top),
                (region.right, region.bottom),
                (region.left, region.bottom),
            ]],
            dtype=np.float32,
        )
        source = cv2.perspectiveTransform(canonical, inverse.astype(np.float32))[0]
        overlays.append(
            RegionOverlay(
                region_key=region.key,
                label_key=REGION_LABEL_KEYS[region.key],
                source_corners=tuple((float(x), float(y)) for x, y in source),
            )
        )
    return tuple(overlays)


def card_region_overlays(
    layout_version: str, *, aligned_image: Image.Image | None = None,
) -> tuple[RegionOverlay, ...]:
    """Return crop rectangles in the coordinates of the rectified card image."""
    return project_region_overlays(
        IDENTITY_TRANSFORM, layout_version=layout_version, aligned_image=aligned_image,
    )


def rotate_image(image: Image.Image, degrees: int) -> Image.Image:
    """Rotate in exact quarter turns without cropping or guessed geometry."""
    if degrees not in (0, 90, 180, 270):
        raise ValueError("rotation must use quarter turns: 0, 90, 180, or 270 degrees")
    transpose = {
        0: None,
        90: Image.Transpose.ROTATE_90,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_270,
    }[degrees]
    return image.copy() if transpose is None else image.transpose(transpose)


def _order_corners(points: np.ndarray) -> np.ndarray:
    sums = points.sum(axis=1)
    differences = points[:, 0] - points[:, 1]
    return np.asarray(
        (
            points[np.argmin(sums)],
            points[np.argmax(differences)],
            points[np.argmax(sums)],
            points[np.argmin(differences)],
        ),
        dtype=np.float32,
    )


def _geometry_is_plausible(points: np.ndarray, image_area: float) -> bool:
    if cv2.contourArea(points) < image_area * 0.04:
        return False
    if not _corners_are_valid(points, (int(np.max(points[:, 0]) + 1), int(np.max(points[:, 1]) + 1))):
        return False
    for index in range(4):
        previous = points[index - 1] - points[index]
        following = points[(index + 1) % 4] - points[index]
        denominator = float(np.linalg.norm(previous) * np.linalg.norm(following))
        if denominator == 0:
            return False
        cosine = float(np.dot(previous, following) / denominator)
        angle = float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
        if not 35 <= angle <= 145:
            return False
    return True


def _corners_are_valid(points: np.ndarray, image_size: tuple[int, int]) -> bool:
    if points.shape != (4, 2) or not np.isfinite(points).all():
        return False
    width, height = image_size
    if np.any(points[:, 0] < 0) or np.any(points[:, 0] >= width):
        return False
    if np.any(points[:, 1] < 0) or np.any(points[:, 1] >= height):
        return False
    return bool(cv2.isContourConvex(points.reshape(-1, 1, 2).astype(np.float32)))


def _distance(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.linalg.norm(first - second))


def _approximate_quad(contour: np.ndarray) -> np.ndarray | None:
    perimeter = cv2.arcLength(contour, True)
    for epsilon in (0.012, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05):
        polygon = cv2.approxPolyDP(contour, epsilon * perimeter, True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            return polygon.reshape(4, 2).astype(np.float32)
    return None


def _normalize_a6_text_crop(crop: Image.Image) -> Image.Image:
    """Enhance marked A6 handwriting without amplifying blank-paper noise."""
    gray = crop.convert("L")
    pixels = np.asarray(gray, dtype=np.uint8)
    dark_ink = int(np.count_nonzero(pixels < 160))
    if dark_ink < max(10, round(pixels.size * 0.002)):
        return crop
    return ImageOps.autocontrast(gray)


def _a6_print_layout(image: Image.Image) -> str:
    """Distinguish HTML, current PDF, and WK-number PDF print layouts."""
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    peaks = []
    for top, bottom in ((270, 350), (400, 490)):
        # A slight paper curl can spread a long baseline across several rows.
        band = cv2.dilate(ink[top:bottom, 300:900], np.ones((5, 1), np.uint8))
        counts = np.count_nonzero(band, axis=1)
        if int(counts.max()) < 300:
            return CARD_LAYOUT_A6_V2
        peaks.append(top + int(np.argmax(counts)))
    if not (275 <= peaks[0] <= 310 and 405 <= peaks[1] <= 440):
        return CARD_LAYOUT_A6_V2
    # V4 adds a third field on the Lauf/Bahn baseline. The new middle Lauf
    # baseline extends well beyond the old two-field layout's left baseline.
    middle_baseline = ink[976:985, 500:650]
    if int(np.count_nonzero(middle_baseline)) >= 120:
        return CARD_LAYOUT_A6_V4
    return CARD_LAYOUT_A6_V3


def _detect_a6_markers(gray: np.ndarray) -> dict[int, np.ndarray] | None:
    """Return the four outer corners of each unique A6 marker in source pixels.

    A white border is added first: a marker that touches the photo edge has no
    quiet zone otherwise and is silently missed by the ArUco detector.
    """
    pad = max(16, round(max(gray.shape) * 0.02))
    padded = cv2.copyMakeBorder(gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), parameters,
    )
    marker_corners, marker_ids, _rejected = detector.detectMarkers(padded)
    found: dict[int, np.ndarray] = {}
    if marker_ids is None:
        return found
    for marker_id, corners in zip(marker_ids.reshape(-1), marker_corners, strict=True):
        marker_id = int(marker_id)
        if marker_id not in A6_MARKER_CENTERS:
            continue
        if marker_id in found:
            return None
        found[marker_id] = corners.reshape(4, 2).astype(np.float32) - pad
    return found


def _a6_marker_target(marker_id: int) -> np.ndarray:
    """Canonical outer corners (TL, TR, BR, BL) of a printed A6 marker."""
    x, y = A6_MARKER_CENTERS[marker_id]
    half = A6_MARKER_SIZE / 2
    return np.asarray(
        ((x - half, y - half), (x + half, y - half), (x + half, y + half), (x - half, y + half)),
        dtype=np.float32,
    )


def _align_a6_markers(image: Image.Image) -> RectifiedCard | None:
    """Crop and rectify an A6 card upright from its unique ArUco corner IDs.

    Every detected marker contributes its four outer corners, so the card is
    located even if one marker is covered or cut off. Return ``None`` only when
    no A6 marker is present, allowing the legacy-template detector to run. Too
    few, duplicated or geometrically inconsistent markers are held for manual
    review rather than guessed as a legacy card.
    """
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    found = _detect_a6_markers(gray)
    if found is None:
        return _uncertain_a6_alignment(image)
    if not found:
        return None
    if len(found) < A6_MIN_MARKERS:
        return _uncertain_a6_alignment(image)

    marker_ids = sorted(found)
    source_points = np.concatenate([found[index] for index in marker_ids])
    target_points = np.concatenate([_a6_marker_target(index) for index in marker_ids])
    matrix, _mask = cv2.findHomography(source_points, target_points, 0)
    if (
        matrix is None
        or not np.isfinite(matrix).all()
        or abs(float(np.linalg.det(matrix))) < 1e-12
    ):
        return _uncertain_a6_alignment(image)
    projected = cv2.perspectiveTransform(source_points.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    if float(np.max(np.linalg.norm(projected - target_points, axis=1))) > A6_MAX_MARKER_ERROR:
        return _uncertain_a6_alignment(image)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return _uncertain_a6_alignment(image)

    centers = np.asarray(
        [A6_MARKER_CENTERS[index] for index in (0, 1, 3, 2)], dtype=np.float32,
    )
    source_centers = cv2.perspectiveTransform(
        centers.reshape(1, -1, 2), inverse.astype(np.float32),
    )[0]
    image_area = float(image.width * image.height)
    if (
        not np.isfinite(source_centers).all()
        or not cv2.isContourConvex(source_centers.reshape(-1, 1, 2))
        or not _geometry_is_plausible(source_centers, image_area)
    ):
        return _uncertain_a6_alignment(image)

    width, height = A6_CANONICAL_SIZE
    warped = cv2.warpPerspective(
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        matrix,
        A6_CANONICAL_SIZE,
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    page_corners = cv2.perspectiveTransform(
        np.asarray([[(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)]],
                   dtype=np.float32),
        inverse.astype(np.float32),
    )[0]
    aligned_image = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
    result = AlignmentResult(
        quality=AlignmentQuality.ACCEPTED,
        transform=tuple(float(value) for value in matrix.reshape(-1)),
        confidence=len(found) / len(A6_MARKER_CENTERS),
        schema_version=_a6_print_layout(aligned_image),
    )
    return RectifiedCard(
        aligned_image,
        result,
        tuple((float(x), float(y)) for x, y in page_corners),
    )


def _uncertain_a6_alignment(image: Image.Image) -> RectifiedCard:
    return RectifiedCard(
        image.copy(),
        AlignmentResult(
            quality=AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT,
            reason_key="error.alignment_uncertain",
            schema_version=CARD_LAYOUT_A6_V2,
        ),
        (),
    )


def _template_layout_version(image: Image.Image) -> str | None:
    """Return the observed print layout from its heading anchor, or reject it.

    The blank reference and Eugen card use the standard row spacing. Ina's
    card has the same printed field set but its handwriting areas are shifted
    80 canonical pixels down. Detect that variant from the printed title band.
    """
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    height, width = gray.shape
    band_width = slice(int(width * 0.12), int(width * 0.88))
    heading = gray[int(height * 0.025) : int(height * 0.14), band_width]
    lower = gray[int(height * 0.89) : int(height * 0.98), band_width]
    # Use a dark-pixel threshold to distinguish printed strokes from the paper
    # texture/shadows. A higher threshold made completed cards with darker lower
    # fields look upside-down even though their heading anchor was intact.
    heading_ink = int(np.count_nonzero(heading < 60))
    lower_ink = int(np.count_nonzero(lower < 60))
    # No anchor or conflicting anchor means orientation remains a user decision.
    if heading_ink < max(20, lower_ink * 2):
        return None

    header_start = int(height * 0.035)
    header_band = gray[header_start : int(height * 0.19), band_width]
    dark_rows = np.count_nonzero(header_band < 60, axis=1).astype(np.float32)
    if dark_rows.size < 3:
        return None
    smoothed = np.convolve(dark_rows, np.ones(7, dtype=np.float32) / 7, mode="same")
    title_row = header_start + int(np.argmax(smoothed))
    return CARD_LAYOUT_V2 if title_row >= 150 else CARD_LAYOUT_V1
