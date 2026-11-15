from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytest

from startkartenleser.domain.contracts import AlignmentQuality, CheckboxState
from startkartenleser.domain.schema import (
    A6_LINE_RECOGNITION_REGIONS,
    CARD_LAYOUT_A6_V3,
    CARD_LAYOUT_A6_V2,
    CARD_LAYOUT_A6_V4,
)
from startkartenleser.infrastructure.image_pipeline import (
    A6_MARKER_CENTERS,
    A6_CANONICAL_SIZE,
    A6_CHECKBOX_REGIONS,
    A6_LINE_CHECKBOX_REGIONS,
    A6_LINE_TEXT_REGIONS,
    A6_FORM_V4_TEXT_REGIONS,
    A6_TIME_DIGIT_CELLS,
    A6_TEXT_REGIONS,
    CANONICAL_SIZE,
    CARD_LAYOUT_A6_V1,
    CHECKBOX_REGIONS,
    TEXT_REGIONS,
    ImageInputError,
    ImagePolicy,
    align_card,
    crop_card_regions,
    crop_contains_handwriting,
    detect_card_corners,
    load_selected_image,
    project_region_overlays,
    regions_for_layout,
    rectify_card,
    rotate_image,
)
from startkartenleser.infrastructure.workflow_adapters import (
    ConservativeCheckboxProposer,
    TemplateCardAligner,
)


def _synthetic_card(*, heading_y: int = 115) -> Image.Image:
    image = Image.new("RGB", (800, 1000), (55, 55, 55))
    draw = ImageDraw.Draw(image)
    draw.polygon(((100, 70), (650, 90), (640, 860), (115, 840)), fill=(245, 240, 220))
    draw.text((260, heading_y), "STARTKARTE", fill=(35, 35, 35), stroke_width=1)
    return image


def _low_grayscale_contrast_card() -> Image.Image:
    image = Image.new("RGB", (800, 1000), (180, 180, 180))
    draw = ImageDraw.Draw(image)
    draw.polygon(((100, 70), (650, 90), (640, 860), (115, 840)), fill=(180, 190, 170))
    draw.text((260, 115), "STARTKARTE", fill=(35, 35, 35), stroke_width=1)
    return image


def _synthetic_a6_card(
    *,
    marker_ids: tuple[int, ...] = (0, 1, 2, 3),
    rotation: int = 0,
    handwriting: bool = False,
    pdf_form: bool = False,
    wk_field: bool = False,
    marked_gender: str | None = None,
) -> Image.Image:
    width, height = A6_CANONICAL_SIZE
    page = Image.new("RGB", A6_CANONICAL_SIZE, "white")
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    centers = {0: (80, 80), 1: (970, 80), 2: (80, 1400), 3: (970, 1400)}
    marker_size = 78
    for marker_id in marker_ids:
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_size)
        rgb_marker = cv2.cvtColor(marker, cv2.COLOR_GRAY2RGB)
        x, y = centers[marker_id]
        page.paste(
            Image.fromarray(rgb_marker),
            (x - marker_size // 2, y - marker_size // 2),
        )
    draw = ImageDraw.Draw(page)
    lines = (
        (210, 935, 332), (250, 935, 467), (260, 505, 605),
        (235, 515, 875), (620, 935, 875), (200, 515, 1010),
        (620, 935, 1010), (290, 935, 1145), (285, 935, 1280),
    ) if not pdf_form else (
        (210, 935, 290), (250, 935, 424), (260, 505, 598),
        (235, 495, 846), (620, 935, 846), (200, 495, 980),
        (620, 935, 980), (290, 935, 1114), (285, 935, 1248),
    )
    for left, right, y in lines:
        draw.line((left, y, right, y), fill=(20, 20, 20), width=3)
    if wk_field:
        draw.line((225, 980, 385, 980), fill=(20, 20, 20), width=3)
        draw.line((475, 980, 650, 980), fill=(20, 20, 20), width=3)
        draw.line((750, 980, 935, 980), fill=(20, 20, 20), width=3)
    for gender, left in (("female", 580 if pdf_form else 590), ("male", 790 if pdf_form else 805)):
        top = 565 if pdf_form else 573
        draw.rectangle((left, top, left + 36, top + 34), outline=(20, 20, 20), width=5)
        if gender == marked_gender:
            draw.line((left + 7, top + 7, left + 29, top + 27), fill=(20, 20, 20), width=5)
            draw.line((left + 7, top + 27, left + 29, top + 7), fill=(20, 20, 20), width=5)
    if handwriting:
        draw.line((320, 260, 400, 290), fill=(35, 35, 35), width=5)

    source_quad = np.asarray(
        ((160, 90), (1290, 145), (1240, 1610), (135, 1545)),
        dtype=np.float32,
    )
    target_quad = np.asarray(
        ((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)),
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(target_quad, source_quad)
    warped = cv2.warpPerspective(
        np.asarray(page),
        matrix,
        (1450, 1700),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(155, 155, 155),
    )
    result = Image.fromarray(warped)
    return result.rotate(rotation, expand=True) if rotation else result


def test_load_selected_image_bounds_decoding_and_preview(tmp_path: Path) -> None:
    path = tmp_path / "card.png"
    source = Image.new("RGB", (400, 200), "white")
    exif = source.getexif()
    exif[274] = 6
    source.save(path, exif=exif)

    loaded = load_selected_image(path, ImagePolicy(preview_size=(100, 100)))

    assert loaded.format == "PNG"
    assert loaded.image.size == (200, 400)
    assert loaded.preview.size == (50, 100)
    assert loaded.image.mode == "RGB"


def test_image_file_size_is_checked_before_decode(tmp_path: Path) -> None:
    path = tmp_path / "too-large.png"
    path.write_bytes(b"not decoded")

    with pytest.raises(ImageInputError) as error:
        load_selected_image(path, ImagePolicy(max_file_bytes=5))

    assert error.value.localization_key == "error.image_too_large"


def test_pixel_limit_is_checked_before_load(tmp_path: Path) -> None:
    path = tmp_path / "pixels.png"
    Image.new("RGB", (20, 20)).save(path)

    with pytest.raises(ImageInputError) as error:
        load_selected_image(path, ImagePolicy(max_pixels=399))

    assert error.value.localization_key == "error.image_too_large"


def test_only_png_and_jpeg_are_supported(tmp_path: Path) -> None:
    path = tmp_path / "animated.gif"
    Image.new("RGB", (10, 10)).save(path, format="GIF")

    with pytest.raises(ImageInputError) as error:
        load_selected_image(path)

    assert error.value.localization_key == "error.unsupported_image"


def test_corrupt_image_has_stable_error_without_exposing_file_path(tmp_path: Path) -> None:
    path = tmp_path / "private-name.jpg"
    path.write_bytes(b"broken")

    with pytest.raises(ImageInputError) as error:
        load_selected_image(path)

    assert error.value.localization_key == "error.image_unreadable"
    assert str(path) not in str(error.value)


def test_auto_alignment_detects_and_rectifies_synthetic_perspective_card() -> None:
    source = _synthetic_card()

    corners = detect_card_corners(source)
    aligned = align_card(source)

    assert corners is not None
    assert aligned is not None
    assert aligned.image.size == CANONICAL_SIZE
    assert aligned.result.quality is AlignmentQuality.ACCEPTED
    assert len(aligned.result.transform) == 9


def test_paper_color_fallback_detects_card_when_grayscale_edge_is_weak() -> None:
    source = _low_grayscale_contrast_card()

    corners = detect_card_corners(source)
    aligned = align_card(source)

    assert corners is not None
    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.ACCEPTED


def test_auto_alignment_rejects_an_image_without_a_card_boundary() -> None:
    source = Image.new("RGB", (800, 1000), (200, 200, 200))

    assert detect_card_corners(source) is None
    assert align_card(source) is None


def test_auto_alignment_requires_heading_anchor_and_rejects_upside_down_cards() -> None:
    upright = align_card(_synthetic_card())
    upside_down = align_card(_synthetic_card().rotate(180))

    assert upright is not None
    assert upright.result.quality is AlignmentQuality.ACCEPTED
    assert upside_down is not None
    assert upside_down.result.quality is AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT
    assert upside_down.result.reason_key == "error.alignment_orientation_uncertain"


def test_heading_anchor_selects_expanded_print_layout_and_offsets_all_rois() -> None:
    source = _synthetic_card(heading_y=165)

    aligned = align_card(source)

    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.ACCEPTED
    assert aligned.result.schema_version == "card-layout-v2"
    layout_v1 = regions_for_layout("card-layout-v1")
    layout_v2 = regions_for_layout("card-layout-v2")
    assert all(second.top - first.top == 80 for first, second in zip(layout_v1, layout_v2, strict=True))
    boxes = project_region_overlays(aligned.result.transform, layout_version="card-layout-v2")
    assert len(boxes) == len(TEXT_REGIONS) + len(CHECKBOX_REGIONS)


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_a6_aruco_markers_align_and_select_separate_field_layout(rotation: int) -> None:
    source = _synthetic_a6_card(rotation=rotation)

    aligned = align_card(source)
    attempt = TemplateCardAligner().align(source)

    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.ACCEPTED
    assert aligned.result.schema_version == CARD_LAYOUT_A6_V2
    assert aligned.image.size == A6_CANONICAL_SIZE
    assert attempt.result.quality is AlignmentQuality.ACCEPTED
    assert attempt.text_crops == {}
    assert set(attempt.skipped_text_regions) == set(A6_LINE_RECOGNITION_REGIONS)
    assert set(attempt.checkbox_crops) == {"checkbox_female", "checkbox_male"}
    assert all(
        ConservativeCheckboxProposer().propose(key, crop).state is CheckboxState.UNCHECKED
        for key, crop in attempt.checkbox_crops.items()
    )
    assert len(attempt.overlays) == len(A6_LINE_TEXT_REGIONS) + len(A6_LINE_CHECKBOX_REGIONS)
    assert {overlay.region_key for overlay in attempt.overlays} == {
        *A6_LINE_RECOGNITION_REGIONS, "checkbox_female", "checkbox_male",
    }


def test_a6_aligner_only_sends_marked_text_regions_to_ocr() -> None:
    attempt = TemplateCardAligner().align(_synthetic_a6_card(handwriting=True))

    assert attempt.result.quality is AlignmentQuality.ACCEPTED
    assert set(attempt.text_crops) == {"name"}
    assert "name" not in attempt.skipped_text_regions
    assert len(attempt.skipped_text_regions) == len(A6_LINE_RECOGNITION_REGIONS) - 1
    assert len(attempt.overlays) == len(A6_LINE_TEXT_REGIONS) + len(A6_LINE_CHECKBOX_REGIONS)


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
@pytest.mark.parametrize("gender", ("female", "male", None))
def test_pdf_form_baselines_select_distinct_crops_and_detect_gender(rotation, gender):
    from startkartenleser.domain.schema import CARD_LAYOUT_A6_V3
    from startkartenleser.infrastructure.image_pipeline import A6_FORM_TEXT_REGIONS

    attempt = TemplateCardAligner().align(
        _synthetic_a6_card(pdf_form=True, rotation=rotation, marked_gender=gender)
    )
    assert attempt.result.schema_version == CARD_LAYOUT_A6_V3
    assert len(attempt.overlays) == len(A6_FORM_TEXT_REGIONS) + 2
    for key, crop in attempt.checkbox_crops.items():
        expected = CheckboxState.CHECKED if key == f"checkbox_{gender}" else CheckboxState.UNCHECKED
        assert ConservativeCheckboxProposer().propose(key, crop).state is expected
    time_region = next(region for region in A6_FORM_TEXT_REGIONS if region.key == "time")
    assert time_region.top <= 1020
    assert time_region.bottom > 1114


def test_a6_pdf_form_with_wk_box_selects_v4_crops():
    attempt = TemplateCardAligner().align(
        _synthetic_a6_card(pdf_form=True, wk_field=True)
    )

    assert attempt.result.schema_version == CARD_LAYOUT_A6_V4
    assert "wk_number" in {region.key for region in A6_FORM_V4_TEXT_REGIONS}
    assert attempt.text_crops == {}
    assert "wk_number" in attempt.skipped_text_regions
    assert len(attempt.overlays) == len(A6_FORM_V4_TEXT_REGIONS) + 2


def test_a6_line_crop_geometry_covers_all_fields_and_one_continuous_time_line() -> None:
    page = Image.new("RGB", A6_CANONICAL_SIZE, "white")
    crops = crop_card_regions(page, layout_version=CARD_LAYOUT_A6_V2)

    assert tuple(crops) == tuple(
        region.key for region in (*A6_LINE_TEXT_REGIONS, *A6_LINE_CHECKBOX_REGIONS)
    )
    assert set(crops) == {*A6_LINE_RECOGNITION_REGIONS, "checkbox_female", "checkbox_male"}
    for region in (*A6_LINE_TEXT_REGIONS, *A6_LINE_CHECKBOX_REGIONS):
        assert crops[region.key].size == (
            region.right - region.left,
            region.bottom - region.top,
        )
    assert crops["time"].size == (640, 103)


def test_a6_form_v4_crop_geometry_includes_independent_wk_number_box() -> None:
    page = Image.new("RGB", A6_CANONICAL_SIZE, "white")
    crops = crop_card_regions(page, layout_version=CARD_LAYOUT_A6_V4)

    assert set(crops) == {
        *(region.key for region in A6_FORM_V4_TEXT_REGIONS),
        "checkbox_female", "checkbox_male",
    }
    assert crops["wk_number"].size == (165, 53)
    assert crops["position"].size == (325, 88)
    assert crops["heat"].size == (185, 70)
    assert crops["lane"].size == (190, 70)


@pytest.mark.parametrize("path", sorted(
    path for path in (Path(__file__).parents[1] / "tests" / "testfotos").glob("*.jpg")
    if not path.stem.endswith("-v1")
), ids=lambda path: path.name)
def test_latest_reference_photos_align_to_the_upright_card(path: Path) -> None:
    source = load_selected_image(path).image
    attempt = TemplateCardAligner().align(source)
    aligned = align_card(source)

    assert attempt.result.quality is AlignmentQuality.ACCEPTED
    assert attempt.result.schema_version in {CARD_LAYOUT_A6_V3, CARD_LAYOUT_A6_V4}
    assert aligned is not None and aligned.image.size == A6_CANONICAL_SIZE
    visible_markers = tuple(sorted(_detected_marker_centers(source)))
    assert len(visible_markers) >= 3
    _assert_markers_at_canonical_corners(aligned.image, expected=visible_markers)


def test_handwriting_gate_ignores_blank_crops_and_keeps_ink() -> None:
    blank = Image.new("L", (100, 40), 245)
    marked = blank.copy()
    ImageDraw.Draw(marked).line((20, 20, 70, 22), fill=25, width=3)

    assert not crop_contains_handwriting(blank)
    assert crop_contains_handwriting(marked)


def test_incomplete_a6_marker_set_is_not_misclassified_as_a_legacy_card() -> None:
    source = _synthetic_a6_card(marker_ids=(0, 1))

    aligned = align_card(source)

    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT
    assert aligned.result.schema_version == CARD_LAYOUT_A6_V2


@pytest.mark.parametrize("missing", (0, 1, 2, 3))
@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_three_a6_markers_still_crop_the_upright_card(missing: int, rotation: int) -> None:
    present = tuple(index for index in (0, 1, 2, 3) if index != missing)
    source = _synthetic_a6_card(marker_ids=present, rotation=rotation)

    aligned = align_card(source)

    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.ACCEPTED
    assert aligned.image.size == A6_CANONICAL_SIZE
    _assert_markers_at_canonical_corners(aligned.image, present)


def test_marker_touching_the_photo_edge_is_still_detected() -> None:
    source = _synthetic_a6_card(rotation=90)
    gray = np.asarray(source.convert("L"))
    rows = np.flatnonzero((gray < 60).any(axis=1))
    # Cut the photo exactly at the outermost marker edge, leaving no quiet zone.
    edge_touching = source.crop((0, int(rows[0]), source.width, source.height))

    aligned = align_card(edge_touching)

    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.ACCEPTED
    assert aligned.result.confidence == 1.0
    _assert_markers_at_canonical_corners(aligned.image)


def _assert_markers_at_canonical_corners(
    image: Image.Image, expected: tuple[int, ...] = (0, 1, 2, 3),
) -> None:
    found = _detected_marker_centers(image)
    assert set(expected) <= set(found)
    for index in expected:
        assert np.linalg.norm(found[index] - np.asarray(A6_MARKER_CENTERS[index])) < 8


def _detected_marker_centers(image: Image.Image) -> dict[int, np.ndarray]:
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
        cv2.aruco.DetectorParameters(),
    )
    corners, ids, _ = detector.detectMarkers(np.asarray(image.convert("L")))
    if ids is None:
        return {}
    return {
        int(index): corner.reshape(4, 2).mean(axis=0)
        for index, corner in zip(ids.ravel(), corners)
    }


def test_a6_crop_geometry_is_bounded_and_versioned() -> None:
    page = Image.new("RGB", A6_CANONICAL_SIZE, "white")

    crops = crop_card_regions(page, layout_version=CARD_LAYOUT_A6_V1)

    expected = (*A6_TEXT_REGIONS, *A6_CHECKBOX_REGIONS)
    assert tuple(crops) == tuple(region.key for region in expected)
    for region in expected:
        if region.key in A6_TIME_DIGIT_CELLS:
            continue
        assert crops[region.key].size == (
            region.right - region.left,
            region.bottom - region.top,
        )
    assert crops["time_minutes"].size == (72, 61)
    assert crops["time_seconds"].size == (72, 61)
    assert crops["time_fraction"].size == (111, 61)
    assert tuple(len(A6_TIME_DIGIT_CELLS[key]) for key in (
        "time_minutes",
        "time_seconds",
        "time_fraction",
    )) == (2, 2, 3)


def test_a6_empty_rois_do_not_autocontrast_blank_paper() -> None:
    image = Image.new("RGB", A6_CANONICAL_SIZE, (245, 245, 245))

    crops = crop_card_regions(image, layout_version=CARD_LAYOUT_A6_V1)

    assert all(low >= 245 for low, _high in crops["time_minutes"].getextrema())
    assert all(low >= 245 for low, _high in crops["name"].getextrema())


def test_a6_marked_text_roi_uses_contrast_normalization() -> None:
    image = Image.new("RGB", A6_CANONICAL_SIZE, (220, 220, 220))
    ImageDraw.Draw(image).line((200, 320, 300, 320), fill=(150, 150, 150), width=3)

    crops = crop_card_regions(image, layout_version=CARD_LAYOUT_A6_V1)

    assert crops["name"].mode == "L"
    assert crops["name"].getextrema() == (0, 255)


def test_supplied_blank_reference_aligns_and_exposes_template_regions() -> None:
    reference_path = Path(__file__).parents[1] / "docs" / "Startkarte_empty.jpg"
    image = load_selected_image(reference_path).image

    aligned = align_card(image)

    assert aligned is not None
    assert aligned.result.quality is AlignmentQuality.ACCEPTED
    assert set(crop_card_regions(aligned.image)) == {
        region.key for region in (*TEXT_REGIONS, *CHECKBOX_REGIONS)
    }
    attempt = TemplateCardAligner().align(image)
    assert attempt.result.quality is AlignmentQuality.ACCEPTED
    assert len(attempt.overlays) == len(TEXT_REGIONS) + len(CHECKBOX_REGIONS)


def test_manual_corners_are_perspective_corrected_with_typed_quality() -> None:
    source = _synthetic_card()
    points = ((100.0, 70.0), (650.0, 90.0), (640.0, 860.0), (115.0, 840.0))

    aligned = rectify_card(source, points)

    assert aligned.image.size == CANONICAL_SIZE
    assert aligned.result.quality is AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT
    assert aligned.corners == points


@pytest.mark.parametrize(
    "corners",
    [
        ((0, 0), (1, 0), (1, 1)),
        ((0, 0), (700, 900), (0, 900), (700, 0)),
        ((-1, 0), (700, 0), (700, 900), (0, 900)),
    ],
)
def test_invalid_manual_corners_are_rejected(corners) -> None:
    with pytest.raises(ValueError):
        rectify_card(_synthetic_card(), corners)


def test_field_and_checkbox_regions_are_bounded_and_stably_ordered() -> None:
    image = Image.new("RGB", CANONICAL_SIZE, "white")

    crops = crop_card_regions(image)

    expected_regions = (*TEXT_REGIONS, *CHECKBOX_REGIONS)
    assert tuple(crops) == tuple(region.key for region in expected_regions)
    assert len(crops) == 10
    for region in expected_regions:
        assert crops[region.key].size == (
            region.right - region.left,
            region.bottom - region.top,
        )


def test_handwriting_regions_include_upper_margin_and_wider_year_entry() -> None:
    regions = {region.key: region for region in regions_for_layout("card-layout-v1")}

    assert regions["name"].top == 145
    assert regions["first_name"].top == 295
    assert regions["year"].left == 270
    assert regions["year"].right == 470
    assert regions["year"].top == 425


def test_crop_regions_project_back_to_labeled_source_image_boxes() -> None:
    source = _synthetic_card()
    source_corners = ((100.0, 70.0), (650.0, 90.0), (640.0, 860.0), (115.0, 840.0))
    aligned = rectify_card(source, source_corners, quality=AlignmentQuality.ACCEPTED)

    overlays = project_region_overlays(aligned.result.transform)
    expected_regions = (*TEXT_REGIONS, *CHECKBOX_REGIONS)

    assert [overlay.region_key for overlay in overlays] == [
        region.key for region in expected_regions
    ]
    assert all(overlay.label_key.startswith("field.") for overlay in overlays)
    matrix = np.asarray(aligned.result.transform, dtype=np.float32).reshape(3, 3)
    for overlay, region in zip(overlays, expected_regions, strict=True):
        projected = cv2.perspectiveTransform(
            np.asarray([overlay.source_corners], dtype=np.float32), matrix
        )[0]
        expected = np.asarray(
            (
                (region.left, region.top),
                (region.right, region.top),
                (region.right, region.bottom),
                (region.left, region.bottom),
            ),
            dtype=np.float32,
        )
        assert np.allclose(projected, expected, atol=1e-3)


def test_crop_requires_a_canonical_aligned_card() -> None:
    with pytest.raises(ValueError, match="aligned card"):
        crop_card_regions(Image.new("RGB", (100, 100)))


@pytest.mark.parametrize("degrees", [0, 90, 180, 270])
def test_quarter_turn_rotation_preserves_all_pixels(degrees: int) -> None:
    image = Image.new("RGB", (20, 10), "red")

    rotated = rotate_image(image, degrees)

    assert rotated.size == ((10, 20) if degrees in (90, 270) else (20, 10))
    assert rotated.getpixel((0, 0)) == (255, 0, 0)


def test_arbitrary_rotation_is_not_silently_cropped() -> None:
    with pytest.raises(ValueError, match="quarter turns"):
        rotate_image(Image.new("RGB", (20, 10)), 45)
