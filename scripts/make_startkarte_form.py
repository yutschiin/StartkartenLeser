"""Generate the A6 Startkarte as a PDF whose upper half is a fillable form.

Name, Vorname, Jahrgang and Geschlecht can be typed on a laptop or phone; the
lower half stays a printed handwriting area for the TSV. Layout and ArUco
markers match docs/startkarte-a6-template.html (DICT_4X4_50, IDs 0-3).

    .venv/bin/pip install -e ".[forms]"
    .venv/bin/python scripts/make_startkarte_form.py
    .venv/bin/python scripts/make_startkarte_form.py --a4
    .venv/bin/python scripts/make_startkarte_form.py --a4 --reference-csv tests/reference_data.csv

The A4 sheet contains four independent forms at 105 x 148 mm with cutting guides.
Print on A4 at actual size / 100%, not "fit to page". Printers with margins
larger than the marker inset may require borderless mode or reduced scaling.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re

from reportlab.lib.colors import Color, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "startkarte-a6-form.pdf"

WIDTH_MM, HEIGHT_MM = 105, 148
MARKER_MM = 9
MARKERS = {
    0: "111111/101001/110101/111001/111011/111111",
    1: "111111/111111/100001/101101/101011/111111",
    2: "111111/111001/111001/111011/100101/111111",
    3: "111111/101101/101101/110111/110011/111111",
}
INK = Color(0.09, 0.15, 0.18)
LABEL = Color(0.2, 0.29, 0.33)
TITLE = Color(0.08, 0.23, 0.33)
MUTED = Color(0.42, 0.47, 0.49)
FIELD_FILL = Color(0.9, 0.95, 1.0)
LEFT, RIGHT = 12, 93


def top(canvas_: canvas.Canvas, mm_from_top: float) -> float:
    return HEIGHT_MM * mm - mm_from_top * mm


def draw_marker(c: canvas.Canvas, marker_id: int, left_mm: float, top_mm: float) -> None:
    box = MARKER_MM * mm
    x, y = left_mm * mm, top(c, top_mm) - box
    c.setFillColor(white)
    c.rect(x, y, box, box, stroke=0, fill=1)
    inner = box - 1.2 * mm
    cell = inner / 6
    # A solid black square with white cells avoids hairline seams between black cells.
    c.setFillColor(Color(0.07, 0.07, 0.07))
    c.rect(x + 0.6 * mm, y + 0.6 * mm, inner, inner, stroke=0, fill=1)
    c.setFillColor(white)
    for row, bits in enumerate(MARKERS[marker_id].split("/")):
        for col, bit in enumerate(bits):
            if bit == "0":
                c.rect(x + 0.6 * mm + col * cell, y + 0.6 * mm + (5 - row) * cell, cell, cell, stroke=0, fill=1)


def label(c: canvas.Canvas, text: str, x_mm: float, baseline_mm: float) -> float:
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x_mm * mm, top(c, baseline_mm) + 0.4 * mm, text)
    return x_mm + c.stringWidth(text, "Helvetica-Bold", 7.5) / mm + 1.5


def write_line(c: canvas.Canvas, start_mm: float, end_mm: float, baseline_mm: float) -> None:
    c.setStrokeColor(INK)
    c.setLineWidth(0.35 * mm)
    c.line(start_mm * mm, top(c, baseline_mm), end_mm * mm, top(c, baseline_mm))


def static_field(c: canvas.Canvas, text: str, x0: float, x1: float, baseline: float) -> None:
    write_line(c, label(c, text, x0, baseline), x1, baseline)


def form_field(
    c: canvas.Canvas, text: str, name: str, x0: float, x1: float, baseline: float, maxlen: int | None = None,
    value: str = "",
) -> None:
    start = label(c, text, x0, baseline)
    write_line(c, start, x1, baseline)
    c.acroForm.textfield(
        name=name, value=value, tooltip=text.rstrip(":"), x=start * mm, y=top(c, baseline) + 0.4 * mm,
        width=(x1 - start) * mm, height=7 * mm, borderWidth=0, borderColor=None, fillColor=FIELD_FILL,
        textColor=INK, fontName="Helvetica", fontSize=11, maxlen=maxlen, fieldFlags="", relative=True,
    )
    _center_textfield(c, value, (x1 - start) * mm, 7 * mm, "Helvetica", 11)


def _center_textfield(
    c: canvas.Canvas, value: str, width: float, height: float, font_name: str, font_size: float,
) -> None:
    """Center values horizontally and place their initial appearance near the bottom."""
    field_ref = c.acroForm.fields[-1]
    field = c._doc.idToObject[field_ref.name]
    field.dict["Q"] = 1  # PDF text alignment: centered.
    if not value:
        return

    appearance_ref = field.dict["AP"]["N"]
    appearance = c._doc.idToObject[appearance_ref.name]
    text_width = pdfmetrics.stringWidth(value, font_name, font_size)
    _, descent = pdfmetrics.getAscentDescent(font_name, font_size)
    x = max(0.0, (width - text_width) / 2)
    # Keep the text baseline near the bottom of the field so the printed value
    # sits close to the writing line rather than floating high in the widget.
    baseline = -descent + 1.5
    appearance.content = re.sub(
        r"1 0 0 1 [^\s]+ [^\s]+ Tm",
        f"1 0 0 1 {x:.3f} {baseline:.3f} Tm",
        appearance.content,
        count=1,
    )


def draw_card(c: canvas.Canvas, prefix: str = "", participant: dict[str, str] | None = None) -> None:
    participant = participant or {}
    edge = 3.5
    draw_marker(c, 0, edge, edge)
    draw_marker(c, 1, WIDTH_MM - edge - MARKER_MM, edge)
    draw_marker(c, 2, edge, HEIGHT_MM - edge - MARKER_MM)
    draw_marker(c, 3, WIDTH_MM - edge - MARKER_MM, HEIGHT_MM - edge - MARKER_MM)

    c.setFillColor(TITLE)
    c.setFont("Helvetica", 12)
    c.drawString(LEFT * mm, top(c, 19), "Pharmaphant-Schwimmfest")
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(RIGHT * mm, top(c, 19), "STARTKARTE")
    c.setStrokeColor(INK)
    c.setLineWidth(0.45 * mm)
    c.line(LEFT * mm, top(c, 21.5), RIGHT * mm, top(c, 21.5))

    def row(index: int) -> float:
        return 29 + index * 13.4

    form_field(c, "Name:", prefix + "name", LEFT, RIGHT, row(0), value=participant.get("name", ""))
    form_field(c, "Vorname:", prefix + "first_name", LEFT, RIGHT, row(1), value=participant.get("first_name", ""))
    form_field(c, "Jahrgang:", prefix + "year", LEFT, 50, row(2) + 4, maxlen=4, value=participant.get("year", ""))

    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(77 * mm, top(c, row(2) - 1), "Geschlecht")
    c.setFont("Helvetica", 8)
    for text, name, x in (("Mädchen", "female", 58), ("Junge", "male", 79)):
        c.acroForm.checkbox(
            name=prefix + name, tooltip=text, x=x * mm, y=top(c, row(2) + 4.5), size=3.8 * mm, borderWidth=1.6,
            borderColor=INK, fillColor=white, buttonStyle="cross", forceBorder=True, relative=True,
            checked=participant.get("gender") == text,
        )
        c.setFillColor(LABEL)
        c.drawString((x + 5.2) * mm, top(c, row(2) + 4.5) + 1 * mm, text)

    c.setStrokeColor(Color(0.32, 0.39, 0.42))
    c.setLineWidth(0.35 * mm)
    c.setDash(1.2, 1.2)
    c.line(LEFT * mm, top(c, row(3) + 2), RIGHT * mm, top(c, row(3) + 2))
    c.setDash()
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(52.5 * mm, top(c, row(3) + 5.5), "wird vom TSV ausgefüllt!")

    static_field(c, "Strecke:", LEFT, 49, row(4) + 2)
    static_field(c, "Lage:", 55, RIGHT, row(4) + 2)
    static_field(c, "WK-Nr.:", LEFT, 38.5, row(5) + 2)
    static_field(c, "Lauf:", 40, 65, row(5) + 2)
    static_field(c, "Bahn:", 67, RIGHT, row(5) + 2)
    static_field(c, "Erzielte Zeit:", LEFT, RIGHT, row(6) + 2)
    static_field(c, "Zeitnehmer:", LEFT, RIGHT, row(7) + 2)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(52.5 * mm, top(c, 139.5), "Bitte gut lesbar in die vorgesehenen Felder schreiben.")


def build(output: Path, *, a4: bool = False, participants: list[dict[str, str]] | None = None) -> None:
    c = canvas.Canvas(str(output), pagesize=A4 if a4 else (WIDTH_MM * mm, HEIGHT_MM * mm))
    c.setTitle("Startkarten A4 – vier ausfüllbare Karten" if a4 else "Startkarte A6 – ausfüllbar")
    c.setAuthor("StartkartenLeser")
    c.setSubject("Name, Vorname, Jahrgang und Geschlecht am Gerät ausfüllen; Rest handschriftlich")
    c.setViewerPreference("PrintScaling", "None")

    cards = participants if participants is not None else [{} for _ in range(4 if a4 else 1)]
    per_page = 4 if a4 else 1
    for offset in range(0, len(cards), per_page):
        if offset:
            c.showPage()
        if not a4:
            draw_card(c, prefix=f"card_{offset + 1}_" if participants is not None else "", participant=cards[offset])
            continue
        # Two 148 mm rows leave 1 mm on A4; keep half above and below the cards.
        for index, participant in enumerate(cards[offset:offset + 4]):
            c.saveState()
            c.translate((index % 2) * WIDTH_MM * mm, (0.5 + (1 - index // 2) * HEIGHT_MM) * mm)
            draw_card(c, prefix=f"card_{offset + index + 1}_", participant=participant)
            c.restoreState()
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.2 * mm)
        c.setDash(2 * mm, 2 * mm)
        c.line(105 * mm, 0, 105 * mm, 297 * mm)
        for baseline in (0.5, 148.5, 296.5):
            c.line(0, baseline * mm, 210 * mm, baseline * mm)
    c.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--a4", action="store_true", help="Four full-size cards on one A4 sheet")
    parser.add_argument("--reference-csv", type=Path, help="Prefill participant fields from a reference CSV")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    participants = None
    if arguments.reference_csv:
        with arguments.reference_csv.open(encoding="utf-8-sig", newline="") as source:
            participants = list(csv.DictReader(source))
        if not participants:
            parser.error("Reference CSV contains no participants")
        for index, participant in enumerate(participants, start=1):
            if any(not participant.get(key) for key in ("name", "first_name", "year", "gender")):
                parser.error(f"Missing participant data in row {index}")
            if not participant["year"].isascii() or not participant["year"].isdigit() or len(participant["year"]) != 4:
                parser.error(f"Invalid birth year in row {index}")
            if participant["gender"] not in ("Mädchen", "Junge"):
                parser.error(f"Unsupported gender in row {index}")
    output = arguments.output or (
        DEFAULT_OUTPUT.with_name("startkarten-test-a4-form.pdf" if arguments.a4 else "startkarten-test-a6-form.pdf")
        if participants is not None else
        DEFAULT_OUTPUT.with_name("startkarten-a4-form.pdf") if arguments.a4 else DEFAULT_OUTPUT
    )
    build(output, a4=arguments.a4, participants=participants)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
