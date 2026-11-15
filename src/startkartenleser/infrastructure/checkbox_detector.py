"""Conservative mark proposals for one isolated checkbox ROI at a time."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import cv2
from PIL import Image, ImageOps

from startkartenleser.domain.contracts import (
    CheckboxState,
    CheckboxValue,
    FieldProvenance,
)


@dataclass(frozen=True)
class CheckboxThresholds:
    unchecked_max_ink: float = 0.045
    checked_min_ink: float = 0.06
    # Printed form crosses are thicker than pen ticks; solid fills remain ambiguous.
    checked_max_ink: float = 0.60
    contrast_margin: int = 35
    interior_margin_ratio: float = 0.27
    min_mark_component_fraction: float = 0.35
    min_mark_width_ratio: float = 0.25
    min_mark_height_ratio: float = 0.25
    min_mark_fill_ratio: float = 0.12
    max_blank_fill_ratio: float = 0.08
    max_blank_components: int = 20


def propose_checkbox_state(
    field_key: str,
    crop: Image.Image,
    thresholds: CheckboxThresholds = CheckboxThresholds(),
) -> CheckboxValue:
    """Classify a single crop; ambiguous/noisy ink is always ``UNKNOWN``.

    The printed box border is excluded from scoring. The detector deliberately
    does not compare the two gender boxes and does not consult text OCR output.
    """
    if not isinstance(crop, Image.Image) or crop.width < 8 or crop.height < 8:
        return CheckboxValue(field_key, CheckboxState.UNKNOWN, FieldProvenance.OCR)
    if not 0 <= thresholds.unchecked_max_ink < thresholds.checked_min_ink:
        raise ValueError("unchecked and checked ink thresholds overlap")
    if not 0 < thresholds.checked_max_ink <= 1:
        raise ValueError("checked maximum ink must be between zero and one")
    if thresholds.contrast_margin < 1:
        raise ValueError("contrast margin must be positive")

    gray = ImageOps.grayscale(crop)
    margin_x = max(1, round(gray.width * thresholds.interior_margin_ratio))
    margin_y = max(1, round(gray.height * thresholds.interior_margin_ratio))
    if margin_x * 2 >= gray.width or margin_y * 2 >= gray.height:
        return CheckboxValue(field_key, CheckboxState.UNKNOWN, FieldProvenance.OCR)
    interior = np.asarray(gray, dtype=np.uint8)[
        margin_y : gray.height - margin_y,
        margin_x : gray.width - margin_x,
    ]
    paper = float(np.percentile(np.asarray(gray), 90))
    if float(np.mean(interior < paper - thresholds.contrast_margin)) > 0.85:
        return CheckboxValue(field_key, CheckboxState.UNKNOWN, FieldProvenance.OCR)
    # Compare against a local paper/background estimate instead of one absolute
    # gray value. The three supplied photos have noticeably different paper
    # brightness and color; fixed thresholds turned unmarked boxes into ink.
    local_background = cv2.GaussianBlur(interior, (0, 0), sigmaX=5)
    ink_mask = np.asarray(
        interior.astype(np.int16)
        < local_background.astype(np.int16) - thresholds.contrast_margin,
        dtype=np.uint8,
    )
    ink_count = int(np.count_nonzero(ink_mask))
    ink_ratio = float(ink_count) / interior.size
    component_count, _, component_stats, _ = cv2.connectedComponentsWithStats(
        ink_mask, connectivity=8
    )
    component_index = (
        1 + int(np.argmax(component_stats[1:, cv2.CC_STAT_AREA]))
        if component_count > 1
        else 0
    )
    if component_index:
        left = int(component_stats[component_index, cv2.CC_STAT_LEFT])
        top = int(component_stats[component_index, cv2.CC_STAT_TOP])
        width = int(component_stats[component_index, cv2.CC_STAT_WIDTH])
        height = int(component_stats[component_index, cv2.CC_STAT_HEIGHT])
        area = int(component_stats[component_index, cv2.CC_STAT_AREA])
    else:
        left = top = width = height = area = 0
    connected_fraction = area / ink_count if ink_count else 0
    fill_ratio = area / (width * height) if width and height else 0
    width_ratio = width / interior.shape[1]
    height_ratio = height / interior.shape[0]
    has_mark_shape = (
        connected_fraction >= thresholds.min_mark_component_fraction
        and width_ratio >= thresholds.min_mark_width_ratio
        and height_ratio >= thresholds.min_mark_height_ratio
        and fill_ratio >= thresholds.min_mark_fill_ratio
    )
    has_ambiguous_mark_shape = (
        connected_fraction >= 0.8
        and width_ratio >= 0.2
        and height_ratio >= 0.2
        and fill_ratio >= 0.06
    )

    if (
        thresholds.checked_min_ink <= ink_ratio <= thresholds.checked_max_ink
        and has_mark_shape
    ):
        state = CheckboxState.CHECKED
    elif ink_ratio <= thresholds.unchecked_max_ink:
        # A few isolated pixels are normal paper texture. A faint connected
        # diagonal remains unknown instead of being called an empty box.
        state = (
            CheckboxState.UNKNOWN
            if has_ambiguous_mark_shape
            or component_count - 1 > thresholds.max_blank_components
            or (has_mark_shape and fill_ratio > thresholds.max_blank_fill_ratio)
            else CheckboxState.UNCHECKED
        )
    else:
        state = CheckboxState.UNKNOWN
    return CheckboxValue(field_key, state, FieldProvenance.OCR)
