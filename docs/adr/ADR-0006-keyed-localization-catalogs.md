# ADR-0006: Store all application UI text in keyed locale catalogs

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The first desktop UI is German, but the application should be ready for additional languages without searching through Tk views, dialogs, domain objects, and error handlers for hardcoded copy. The requirement applies to every application-owned string shown or spoken to a user, including accessibility names and errors. Stable field keys, database values, and recognized/user-entered content must remain independent of the display language.

## Decision

- Store all application-owned user-visible and accessibility text in keyed locale resource files under `locales/`; do not embed user-facing wording in Python UI, presenter, domain, or error-handling code.
- Use JSON catalogs with stable namespaced keys (for example `field.name`, `status.needs_review`, `error.image_unreadable`, `accessibility.delete_card`). Ship `locales/de.json` for the initial German UI. Additional languages add catalogs without changing feature/domain code.
- Add a small `TextCatalog` localization boundary. UI code requests a key and supplies named parameters; catalog entries own the full localized message and interpolation wording. Catalog structure must support plural forms and locale-aware formatting.
- Keep domain schema, persisted enums, database keys, and application logic language-neutral. Field and status definitions carry localization keys; never persist translated labels as identifiers. Preserve handwritten OCR candidates and user data exactly as data, not translation strings.
- Resolve the active locale at application startup. For the first release, German is the default and safe fallback. A missing key is a test/development error; never display the raw key or silently fall back to a source-language literal. Validate key completeness, duplicate keys, and interpolation placeholders in automated tests.
- Localize application-supplied titles, labels, buttons, help, status, validation/error text, confirmation prompts, tooltips, file filters, and accessibility text. Native OS dialog chrome may follow the OS locale; any app-supplied dialog text still comes from the catalog.

## Consequences

- A new UI string requires a catalog entry and stable key in the same change; code review can verify copy independently of presentation logic.
- Automated completeness checks are required so no screen displays a missing key.
- Date, number, and duration formatting must use locale-aware formatters while storing canonical locale-independent values.
- OCR text, names, and other user data are not localized or rewritten. Only UI framing around those values is translated.
- The first implementation needs a catalog loader and a JSON catalog, but no third-party i18n framework is required.
