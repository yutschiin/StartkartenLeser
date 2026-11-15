# CSV export format

Export is available for a nonempty Wettkampf only when every card is approved.
Drafts block the entire export rather than being omitted. Export does not change
card review state. Compatibility with a particular meet-management program has
not been certified.

## Encoding and rows

- UTF-8 with a byte-order mark (BOM).
- Semicolon delimiter, CRLF line endings and standard CSV quoting.
- One row per card, in card sequence order.
- Event metadata is repeated on each row. OCR evidence and private image paths
  are not exported.

Exact header order:

```text
csv_version;wettkampf_id;wettkampf_number;distance_m;stroke_key;gender_key;card_id;sequence;name;first_name;year_text;heat;heat_text;lane;lane_text;time_ms;time_text;timekeeper;female_mark;male_mark
```

`csv_version` is `1`. `heat`, `lane` and `time_ms` contain parsed canonical
values when valid; otherwise they are empty. Their `*_text` columns retain the
reviewed text. `gender_key` is `female`, `male`, or `mixed`. Gender marks are
independent and use `unknown`, `checked`, or `unchecked`; they do not determine
the Wettkampf category.

Text cells that could be interpreted as spreadsheet formulas are prefixed with
an apostrophe in the exported representation. Stored values are unchanged. The
browser handles the file download and destination prompts.
