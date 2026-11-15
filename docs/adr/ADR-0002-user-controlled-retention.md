# ADR-0002: User-controlled data retention

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

Startkarten contain personal information. Users need to resume work and to
control deletion of stored cards and Wettkämpfe. There is no cloud archive or
automatic retention service.

## Decision

- Retain card records, recognized values and managed image copies locally until
  the user deletes a card/Wettkampf or removes the application data directory.
- Do not automatically expire or delete saved data.
- Deleting a card or Wettkampf removes its application-managed records and image
  copies. It does not remove the user's original image or a separately exported
  CSV.
- Store data in the documented application-specific directory. The application
  does not control operating-system backups.

## Consequences

- Users must be told where data is stored, how to delete it and that it may remain
  indefinitely until they do so.
- Backups should include the complete data directory, including images.
- Local storage is not encrypted by the application; access depends on the
  operating-system account and device security.
