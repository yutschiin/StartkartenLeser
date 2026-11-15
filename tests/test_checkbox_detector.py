from PIL import Image, ImageDraw

from startkartenleser.domain.contracts import CheckboxState, FieldProvenance
from startkartenleser.infrastructure.checkbox_detector import propose_checkbox_state


def _checkbox(mark: str | None = None) -> Image.Image:
    image = Image.new("L", (64, 64), 245)
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 55, 55), outline=40, width=2)
    if mark == "check":
        draw.line((19, 34, 29, 44, 47, 19), fill=25, width=4)
    elif mark == "faint":
        draw.line((21, 33, 30, 42), fill=180, width=1)
    elif mark == "noise":
        for x in range(19, 47, 4):
            for y in range(20, 47, 4):
                image.putpixel((x, y), 30)
    return image


def test_clear_check_proposes_checked_independently() -> None:
    result = propose_checkbox_state("female", _checkbox("check"))

    assert result.state is CheckboxState.CHECKED
    assert result.provenance is FieldProvenance.OCR


def test_clear_empty_box_proposes_unchecked() -> None:
    result = propose_checkbox_state("male", _checkbox())

    assert result.state is CheckboxState.UNCHECKED


def test_ambiguous_faint_or_noisy_marks_remain_unknown() -> None:
    faint = propose_checkbox_state("female", _checkbox("faint"))
    noisy = propose_checkbox_state("male", _checkbox("noise"))

    assert faint.state is CheckboxState.UNKNOWN
    assert noisy.state is CheckboxState.UNKNOWN


def test_independent_inputs_can_propose_both_boxes_checked() -> None:
    female = propose_checkbox_state("female", _checkbox("check"))
    male = propose_checkbox_state("male", _checkbox("check"))

    assert female.state is CheckboxState.CHECKED
    assert male.state is CheckboxState.CHECKED


def test_invalid_or_tiny_input_is_unknown() -> None:
    assert propose_checkbox_state("female", Image.new("L", (2, 2))).state is CheckboxState.UNKNOWN
    assert propose_checkbox_state("male", None).state is CheckboxState.UNKNOWN  # type: ignore[arg-type]


def test_thick_pdf_cross_is_checked_but_solid_fill_is_ambiguous():
    image = Image.new("L", (40, 42), 245)
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 3, 37, 39), outline=25, width=5)
    draw.line((7, 9, 31, 33), fill=25, width=5)
    draw.line((7, 33, 31, 9), fill=25, width=5)
    assert propose_checkbox_state("male", image).state is CheckboxState.CHECKED
    draw.rectangle((7, 8, 33, 34), fill=25)
    assert propose_checkbox_state("male", image).state is CheckboxState.UNKNOWN
