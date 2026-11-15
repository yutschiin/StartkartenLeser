# ADR-0008: Use a general local application config file

- Status: Accepted
- Date: 2026-11-15

## Context

Before this decision, Wettkampf creation offered five hard-coded Lagen in the
frontend and validated that same fixed set in the Python browser workflow. Clubs
may use additional or differently named Lagen and need to define recognition
synonyms. The OCR correction policy is already loaded from JSON at startup, so
the general application config is the natural place to define both dropdown
options and their recognition rules.

## Decision

Use the local `config.json` file as the single source of truth for
available Lagen, display labels, recognition synonyms, and OCR correction
parameters. The app copies the packaged defaults into its data directory on
first launch and loads the file before starting the local server. The browser
receives the configured dropdown options through bootstrap; the backend accepts
configured values and bounded one-off text values. Editing the file takes effect
after a restart. Existing `recognition-policy.json` files are renamed to
`config.json` when no new config file exists.

Keep the existing five Lagen and current OCR rules as packaged defaults, and
include Flossenschwimmen mit Brett and Freistil mit Flossen with their synonyms.
Also continue to accept the former standalone recognition-policy file format,
using the default Lagen list for those legacy configurations. The additive
SQLite v4 settings table is retained for compatibility with earlier builds but
is not used for Lage configuration. There is no in-app management UI.

## Consequences

- Users edit a local JSON file and restart the app to change Lagen or OCR rules.
- The Python startup path validates the complete file before serving requests;
  malformed or ambiguous configuration prevents startup rather than silently
  changing recognition behavior.
- OCR remains a suggestion; configured synonyms only inform correction and
  comparison, not approval.
- A one-off Lage can be used for a single Wettkampf; reusable OCR synonyms for it
  require adding it to `config.json`.

## Alternatives considered

- Store options in SQLite and manage them in the browser: rejected because the
  user requested a pre-start file and the existing recognition policy already
  has a local JSON loading path.
- Add user-defined values as a free-text field on every Wettkampf: rejected
  because it does not provide reusable values or reusable recognition synonyms.
