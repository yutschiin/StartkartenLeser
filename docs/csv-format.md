# CSV export format

Export is available for a nonempty Wettkampf only when every card is approved.
Drafts block the entire export rather than being omitted. Export does not change
card review state. Compatibility with a particular meet-management program has
not been certified.

## Encoding and rows

- UTF-8 with a byte-order mark (BOM).
- Semicolon delimiter, CRLF line endings and standard CSV quoting.
- One row per card, in card sequence order.
- Rows contain reviewed card data and card identifiers. Wettkampf metadata is
  not included in the CSV; the Wettkampf is used to name the export file.
- OCR evidence and private image paths are not exported.

Exact header order:

```text
csv_version;card_id;sequence;wk_number;name;first_name;year_text;female_mark;male_mark;course;position;heat;heat_text;lane;lane_text;time_ms;time_text;timekeeper
```

`csv_version` is `2`. All values, including Wettkampf number, course, position,
and gender marks, come from the approved card. `heat`, `lane` and `time_ms`
contain parsed canonical values when valid; otherwise they are empty. Their
`*_text` columns retain the reviewed text. Gender marks use `unknown`, `checked`,
or `unchecked`.

Text cells that could be interpreted as spreadsheet formulas are prefixed with
an apostrophe in the exported representation. Stored values are unchanged. The
browser handles the file download and destination prompts.
