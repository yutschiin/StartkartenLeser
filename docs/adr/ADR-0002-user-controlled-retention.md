# ADR-0002: User-controlled data retention

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

Startkarten contain personal information. Users need to return to a session and continue reviewing cards, while having clear control over deletion. The MVP has no export or cloud synchronization.

## Decision

- Retain card image copies and structured session data locally until the user deletes a card/session or removes the application's data.
- Do not automatically expire or delete saved cards in the MVP.
- Provide deletion for an individual card and a complete session, including associated image copies and derived values.
- Store data in a documented, application-specific directory. The application does not control user-managed operating-system backups.

## Consequences

- The application must explain retention, the local data location, and how deletion works.
- Data can remain on the computer indefinitely if the user does not delete it; storage use and this consequence should be communicated.
- User-managed backups may contain sensitive local app data. Do not claim that desktop app data is excluded from backup.
- Deleting an imported card removes the app's stored copy, not the user's original image file.
