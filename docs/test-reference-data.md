# Test reference data

> **Public test fixtures:** These 16 cards and their photos are fictional. They
> contain no real people or real meet entries and are included only for software
> development and testing.

This table lists the 16 fictional cards and their corresponding latest test photos. The machine-readable copy is [`tests/reference_data.csv`](../tests/reference_data.csv); keep its rows and this table in sync when reference cards change.

The latest photo set is [`tests/testfotos/`](../tests/testfotos/); previous photo
versions have been removed. Evaluation excludes Zeitnehmer/timekeeper (nine
fields, 144 observations), though it remains on the cards and in the reference
CSV. Use the [isolated Wettkampf workflow evaluator](feature-designs/wettkampf-workflow-evaluation.md)
with a separate permission-cleared photo directory for future holdout runs.

| # | Name | Vorname | Jahrgang | Geschlecht | Strecke | Lage | Lauf | Bahn | Erzielte Zeit | Zeitnehmer | Foto |
|---:|---|---|---:|---|---|---|---:|---:|---|---|---|
| 01 | Müller | Anna | 2012 | Mädchen | 50 m | Freistil | 1 | 1 | 00:42,18 | K. Weber | karte-01-mueller-anna.jpg |
| 02 | Schneider | Lukas | 2011 | Junge | 50 m | Rücken | 1 | 2 | 00:39,64 | M. Fischer | karte-02-schneider-lukas.jpg |
| 03 | Fischer | Mia | 2013 | Mädchen | 50 m | Brust | 1 | 3 | 00:51,27 | K. Weber | karte-03-fischer-mia.jpg |
| 04 | Weber | Ben | 2010 | Junge | 100 m | Rücken | 1 | 4 | 1:34,92 | S. Bauer | karte-04-weber-ben.jpg |
| 05 | Wagner | Emma | 2012 | Mädchen | 100 m | Freistil | 2 | 1 | 01:24,53 | M. Fischer | karte-05-wagner-emma.jpg |
| 06 | Becker | Paul | 2009 | Junge | 100 m | Rücken | 2 | 2 | 01:18,06 | S. Bauer | karte-06-becker-paul.jpg |
| 07 | Hoffman | Lina | 2014 | Mädchen | 50 m | Rücken | 2 | 3 | 00:47,81 | T. Scholz | karte-07-hoffman-lina.jpg |
| 08 | Schulz | Noah | 2013 | Junge | 50 m | Freistil | 2 | 4 | 00:43,09 | K. Weber | karte-08-schulz-noah.jpg |
| 09 | Koch | Emily | 2011 | Mädchen | 100 m | Brust | 3 | 1 | 01:39,72 | T. Scholz | karte-09-koch-emily.jpg |
| 10 | Richter | Leon | 2012 | Junge | 100 m | Freistil | 3 | 2 | 01:17,38 | M. Fischer | karte-10-richter-leon.jpg |
| 11 | Klein | Sophie | 2010 | Mädchen | 50 m | Schmetterling | 3 | 3 | 00:38,45 | S. Bauer | karte-11-klein-sophie.jpg |
| 12 | Wolf | Elias | 2014 | Junge | 50 m | Brust | 3 | 4 | 00:56,13 | T. Scholz | karte-12-wolf-elias.jpg |
| 13 | Neumann | Mila | 2008 | Mädchen | 100 m | Rücken | 4 | 1 | 01:31,26 | K. Weber | karte-13-neumann-mila.jpg |
| 14 | Schwarz | Felix | 2011 | Junge | 100 m | Schmetterling | 4 | 2 | 01:26,84 | S. Bauer | karte-14-schwarz-felix.jpg |
| 15 | Zimmermann | Ella | 2013 | Mädchen | 50 m | Freistil | 4 | 3 | 00:45,70 | M. Fischer | karte-15-zimmermann-ella.jpg |
| 16 | Braun | Oskar | 2009 | Junge | 100 m | Brust | 4 | 4 | 01:33,58 | T. Scholz | karte-16-braun-oskar.jpg |

## Test photos

Save the current reference photos in [`tests/testfotos/`](../tests/testfotos/). Use this filename format:

`karte-<two-digit-card-number>-<lowercase-name>-<lowercase-first-name>.jpg`

For example, card 07 is `karte-07-hoffman-lina.jpg`. The `image_filename` column in the CSV maps each reference record to its photo. Keep test photos out of application data folders; the application may make its own managed copy during import.
