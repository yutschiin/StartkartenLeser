# Product scope

## Product rules

- A Wettkampf has a positive number and distance in metres, a Lage selected from
  the config or entered for that event, and a Weiblich, Männlich or Mixed group.
  Metadata is set at creation and cannot currently be edited afterward.
- Mixed is an event group, not a participant mark: individual card marks remain
  female/male, and reference comparison does not assume one of them for Mixed.
- A card belongs to one Wettkampf. Older unclassified records keep their
  existing data until the user explicitly moves cards into a new Wettkampf;
  metadata is never inferred from OCR.
- OCR and checkbox detection produce evidence and editable suggestions. They do
  not approve a card, certify correctness or silently replace confirmed user
  values. Event metadata is authoritative; card readings that disagree can be
  shown as warnings.
- Fields may remain blank or unresolved when a card is approved. Approval records
  the user's review, not completeness or OCR correctness.
- A CSV is an explicit download of a snapshot of a nonempty Wettkampf whose
  cards are all approved. It does not delete or alter application data.
- Images and records remain on the local computer until user deletion. Setup may
  download application dependencies or pinned model assets; card data is never
  sent to those services.

## Supported card data

The form covers name, first name, year, female/male marks, event number, course,
stroke, heat, lane, time and timekeeper. Card layouts determine available
alignment and OCR regions. The printed card and handwriting remain the source of
truth; unsafe alignment is not used to invent field crops.

## Limits

User-editable event metadata after creation, custom card templates, manual corner
adjustment, open categories, hosted recognition, synchronization, and certified
compatibility with a specific external meet-management program are outside the
current product scope. OCR accuracy on the included development fixtures is not
a product accuracy claim.

See the [README](../README.md) for user setup and operation,
[architecture](architecture.md) for technical boundaries, and
[CSV format](csv-format.md) for the exact exported data contract.
