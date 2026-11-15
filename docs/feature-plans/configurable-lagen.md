# Feature plan: configurable Lagen

## Goal

Let users configure the Lage choices shown when creating a Wettkampf, including
the synonyms used for OCR recognition, in a local JSON file before launching
the app. There is no in-app configuration UI.

## Architecture fit

- The existing recognition policy is already a validated JSON configuration
  loaded by the Python composition root. Extend that file to also declare
  dropdown choices and their recognition synonyms.
- The startup process loads the complete configuration once, passes the Lage
  choices to the browser bootstrap, and supplies the same synonyms to the OCR
  correction policy.
- Wettkampf records continue to store the selected stable value; no database
  settings endpoint is needed. The v4 `application_settings` table is retained
  only for compatibility with an earlier build.
- Preserve existing user policy files in the former standalone format; they
  are renamed to `config.json` and continue to load with the default Lage list.

## Implementation plan

1. Extend the packaged `config.json` with configured Lage values,
   labels, synonyms, and explicit OCR policy parameters.
2. Validate and load the combined file at startup; seed a user-editable copy in
   the application data directory when none exists.
3. Pass configured options to bootstrap, accept validated one-off Lage text for
   a single Wettkampf, and provide Mixed in the Wettkampfgruppe dropdown; keep
   the configuration UI out of the app.
4. Test JSON validation, synonym-based correction, configured dropdown options,
   update the README/architecture/ADR, and run the relevant suites and build.

## Acceptance criteria

- A fresh installation offers the five standard Lagen plus Flossenschwimmen mit
  Brett and Freistil mit Flossen.
- The user-editable JSON is loaded before the local server starts and options
  appear in Wettkampf creation after restart.
- Configured synonyms drive the existing conservative OCR correction policy.
- A Wettkampf can use a configured Lage or a one-off value typed into the
  autocomplete; its name remains readable in the UI, comparisons, and exports.
- Mixed is accepted as an event group without assuming either participant sex
  checkbox or reporting a gender reference mismatch.
- Invalid, ambiguous, duplicate, oversized, or empty configurations fail
  startup with a clear validation error.
