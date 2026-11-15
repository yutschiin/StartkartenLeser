# ADR-0006: Keyed catalogs for application text

- **Status:** Accepted; German is the only shipped interface language.
- **Date:** 2026-11-03

## Context

Field identifiers, stored values and OCR output must not depend on the language
used to display the interface. Application-owned text should be managed
separately from workflow and domain logic.

## Decision

- Keep backend messages in keyed JSON catalogs under
  `src/startkartenleser/locales/` and frontend messages in a keyed TypeScript
  catalog under `frontend/src/`.
- Keep persisted field/status identifiers language-neutral. Never translate
  handwriting or user-entered values.
- Support named interpolation and one/other plural forms in the Python catalog.
- Use German (`de`) as the current default. Additional languages require
  compatible catalogs and complete UI coverage.

## Current implementation note

Backend catalog tests check required keys, plural forms and placeholders, and
the Python catalog raises on an unknown key. The frontend currently has a
German-only catalog and falls back to displaying an unknown key; it does not yet
have equivalent catalog-completeness validation. Do not claim multi-language
support or complete frontend key validation.
