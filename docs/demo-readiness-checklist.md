# Public source publication and demo-readiness checklist

Use this before making the repository public or presenting the app to someone
who did not set it up. The goal is that people can download the source, understand
the architecture, install, build, run, and test it. This is not a claim that a
prebuilt desktop installer exists. Follow the ordered
[publication task list](publication-readiness-tasks.md), starting with docs.

## Current audit snapshot

- **Public history:** `main` is now a clean root snapshot (`75d88f4`) with no
  inherited commits. Other local experiment branches retain their old history
  and should not be pushed; no remote is configured.
- **Documentation install path was rehearsed from a source archive without Git
  metadata** on Ubuntu 26.04.1/Python 3.14.4. The exact README wheel-build/install
  recipe and no-cache setup also passed in a clean temporary copy. Other
  OS/Python combinations remain unverified.
- **Backend tests passed:** `.venv/bin/python -m pytest -q` — 368 passed.
- **Frontend tests pass:** all **47 tests** pass with the configured 20-second
  timeout. Slow MUI/jsdom tests exceeded Vitest's 5-second default under load;
  the Enter/autosave test passes, and no application behavior change was needed.
- **Frontend typecheck passed.** A production Vite build to a temporary
  directory also passed and emitted the same asset hashes. It reported the
  JavaScript bundle is about 571 kB (above Vite's 500 kB advisory threshold).
- **Secret scan:** targeted patterns found no high-confidence credentials in
  current source or textual Git history. This does not inspect arbitrary binary
  data or detect every secret format.
- **Photo/results cleanup is committed:** current `tests/testfotos/` contains
  only the latest 16 photos and `tests/results/` is ignored. Older photos and
  result CSVs remain retrievable from earlier Git commits unless history is
  rewritten; historical narrative summaries remain in
  [`ocr-test-strategy.md`](ocr-test-strategy.md).
- **Photo clearance:** owner confirms the current card photos contain no real
  people or real meet entries and are cleared for public testing. The README and
  reference-data docs now state this prominently. The unneeded A6 draft PDF was
  removed from the local checkout.
- **Project license:** MIT is at top-level `LICENSE` and declared in
  `pyproject.toml`. Package artifacts include model/frontend notices; the owner
  confirmed the `StartkartenLeser contributors` copyright-holder wording.
- **Third-party notices:** model provenance/license and Python/frontend notice
  files are present. The generated frontend license file matches the currently
  installed locked production dependency closure. Inclusion in a built wheel and
  source archive has been checked.
- **Package/source-archive check passed in a temporary clean copy:** source
  archive and wheel built; `LICENSE`, model/training-data notices, frontend
  assets/licenses, docs, setup files, scripts, reference CSV and all 16 current
  test photos were present. A fresh Python 3.14 Linux venv installed the wheel
  and served its index, JS and CSS over loopback. `setup.sh` succeeded from an
  extracted source archive with pip/npm caches disabled; its no-Git test run
  passed **368 tests**. A source evaluation produced 144 observations with full
  alignment, and a separate wheel-installed one-line OCR inference completed.
  These are development-set smoke checks, not holdout validation; the CSV stayed
  outside the repository. Camera hardware was not tested.
- **Frontend bundle:** `web_static/index.html` references the two new hashed
  assets; a production Vite build reproduced them byte-for-byte. The bundle-size
  advisory remains.

## Checklist

### Documentation first

- [x] Reconcile the README's source setup/build commands with `setup.sh`,
  dependency/lock files, `pyproject.toml`, model provisioning, and npm scripts.
- [x] Document the chosen project license and keep third-party notices separate.
- [x] Rehearse `setup.sh` and backend tests from an extracted source archive on
  Ubuntu 26.04/Python 3.14 with pip/npm caches disabled; package installs and
  model checks passed, then 368 tests passed without Git metadata.
- [ ] Rehearse camera permission, live OCR, and the complete workflow on the
  target browser/machine; the setup rehearsal used cached package downloads.
- [x] Document source archive/wheel build and wheel-install commands. In the
  clean temporary build check, the wheel installed and served the bundled UI;
  no prebuilt desktop installer is promised.
- [x] Architecture docs match current modules and explain request flow,
  persistence/migration, local OCR, export and privacy boundaries. Historical MVP
  docs are labeled as such.
- [x] State the verified environment: Ubuntu 26.04.1/Python 3.14.4, Node
  22.23.3/npm 10.9.9, Chromium 156.0.8078.47. Other OS/Python combinations
  remain unverified and are not claimed as supported.
- [x] Check local documentation links and remove stale links to deleted result
  files and previous photo folders.

### Public-use rights

- [x] Choose and add a top-level MIT project license and declare it in package
  metadata.
- [x] Owner confirmed the copyright-holder text (`StartkartenLeser contributors`)
  in `LICENSE`.
- [x] Check existing redistribution notices: model/training-data attributions,
  Python dependency table, and frontend dependency license bundle are present;
  the frontend bundle matches the installed production dependency closure.
- [x] Verify those notices and `LICENSE` are included in source archive and wheel.
- [x] Owner confirmed the latest reference photos and sample records are fictional,
  contain no real people, and are cleared for public distribution; the README and
  reference-data docs say so prominently.
- [x] Owner confirmed the form mockups/PDFs and remaining design materials are
  project-created and cleared to publish.

### Scope and repository hygiene

- [x] Review the publication changes: latest test photos, no current result
  artifacts, evaluation source/tests, docs, and bundled frontend assets are kept
  intentionally and included in the clean public snapshot.
- [x] Confirm the modified `frontend/src/styles.css` and generated
  `src/startkartenleser/web_static/` assets are from the same build. Keep the
  frontend source and its bundled output together; a clean temp build produced
  byte-identical HTML/CSS/JS assets.
- [x] Confirm the evaluation scripts, module, tests and design note are retained
  as developer tooling; their generated run output is not tracked.
- [x] Exclude the unneeded `docs/Startkarte A6 – Entwurf.pdf` draft from the demo
  commit.
- [x] Confirm old capture folders and result artifacts have been removed and
  `tests/results/` is ignored for future local runs. The latest photos are in the
  canonical tracked `tests/testfotos/` fixture directory.
- [x] Keep local environments, caches, build directories, evaluation outputs,
  and application data out of version control. Do not copy real user data into
  the repository.
- [ ] Decide whether to rewrite Git history to purge old photo/result files and
  agent-checkpoint commit subjects. The current tree is clean of those artifacts,
  but they remain retrievable from earlier commits; rewriting changes commit IDs.

### Install, run, and package

- [x] Follow README setup from a clean source archive on the declared host and
  record the prerequisites: Python 3.14.4, Node 22.23.3/npm 10.9.9, Chromium.
  Node is not needed at runtime after the frontend is bundled.
- [x] Verify `./setup.sh` succeeds from a clean source archive, including model
  checksum validation and Python imports. It succeeded on Linux/Python 3.14.
- [x] Start the wheel-installed app with a dedicated disposable data directory;
  the clean wheel smoke test used `/tmp/opencode/.../wheel-data`.

  ```bash
  .venv/bin/python -m startkartenleser --no-browser --data-dir /tmp/startkartenleser-demo
  ```

  Open the complete printed loopback URL in the target browser. Do not use a
  personal/default data directory for a public demo.
- [x] Build and inspect a source archive/wheel from a clean temporary copy. It
  includes the MIT license, docs, 16 test photos, static assets, model files,
  locale data, and third-party notices. The wheel was installed in a fresh
  Python 3.14 Linux venv and served its UI over loopback.
- [x] Verify the packaged frontend loads from the installed wheel; it served HTML,
  JS, and CSS over loopback using a disposable data directory.
- [x] Run the exact README build/wheel-install recipe in a clean temporary copy.
- [x] Run a real local OCR smoke evaluation using the model packaged in the wheel;
  inference completed using local model files. The host network was available,
  though inference itself does not fetch model assets.
- [ ] Manually test camera permission and the full capture/review/export workflow
  on the actual demo machine and browser.

### Verification and real workflow

- [x] Backend suite: **368 passed** in the repository and from a source archive
  without Git metadata.
- [x] Frontend TypeScript check passed in this audit.
- [x] Raise Vitest's timeout for the slow jsdom/MUI cases and run the complete
  frontend suite: **47 passed**.
- [x] Frontend tests, TypeScript checking, and production build have passed
  (the clean setup rehearsal built the frontend in a temporary source copy):

  ```bash
  npm --prefix frontend test
  npm --prefix frontend run typecheck
  npm --prefix frontend run build
  ```

  Review the generated asset diff; do not discard or overwrite other pending
  frontend work.
- [ ] On the actual demo machine/browser, manually verify camera permission and
  capture, file upload fallback, OCR/manual review, autosave, approval, retake,
  deletion, and CSV export. Automated tests are not camera/device coverage.
- [ ] Rehearse a full path using disposable data: create a Wettkampf, capture at
  least one card, review/edit, approve, export, and restart/reopen. Verify the
  export in the intended meet-management software if compatibility is claimed.
- [ ] Use a known failure/ambiguous-mark example in the demo. Explain that OCR
  creates editable suggestions and approval is a human review step.

### Data, privacy, and secrets

- [x] Owner confirmed the current photos and reference records are fictional,
  contain no real people, and are cleared for public test-data distribution.
- [ ] Keep new local captures/evaluation outputs ignored unless they are
  deliberately reviewed, permission-cleared, minimized fixtures. Do not commit
  databases, copied source images, exports, HTML reports or ZIPs just because
  they are under `tests/`.
- [x] Review the current tracked reference photos against the owner-confirmed
  fictional/public test-data statement.
- [x] Targeted credential/key pattern scans found no high-confidence matches in
  current source or textual Git history. This does not cover every binary format.
- [ ] Decide whether to rewrite Git history to purge old photo/result files; they
  were removed from the current revision but remain in earlier commits. Rewriting
  history changes commit IDs and requires collaborators to reclone.
- [ ] Be precise in the demo: data and OCR are local, but local files/SQLite and
  CSV exports are not encrypted. Explain where data is stored, who can access the
  OS account, how to back it up, and how to remove the disposable demo data.

## Challenge the checklist (things a “green” checklist can still miss)

1. **Passing tests is not OCR quality.** The OCR figures in
   [`ocr-test-strategy.md`](ocr-test-strategy.md) are development-set results;
   geometry/policy were tuned against those examples, and the docs identify a
   reference mismatch. Do not present them as independent accuracy or production
   readiness. Obtain a separate permission-cleared holdout before making such a
   claim.
2. **Local-only is not equivalent to secure or private by default.** Local
   databases, images and downloaded exports are not encrypted. A loopback server
   and per-launch token reduce exposure but do not protect data from other users
   of the same OS account, backups, screenshots, or copied demo folders.
3. **A clean Git status can hide ignored risk.** The ignored capture/result files
   remain on disk. Check ignored files and the actual demo data directory; remove
   them only after deciding whether they are needed and keeping any required
   evidence.
4. **A green test run can miss distribution failure.** Source-tree tests do not
   prove that a built wheel has the right model, browser assets, notices and
   dependencies. Install and launch the artifact produced from a clean checkout.
5. **A successful first run is not an event-day plan.** Camera hardware,
   browser permissions, lighting, focus, network availability during setup,
   power, disk space and a recovery/backup procedure must be rehearsed on the
   actual equipment.
6. **A demo export is not certified integration.** The README already says
   compatibility with a specific meet-management program is not certified. Do
   not imply otherwise without testing a real import round-trip.
7. **Checklist ownership matters.** Assign a person to the remaining decisions
   (test failure, photo provenance, package licensing, demo data
   cleanup) and record a go/no-go. An unchecked item should not silently become
   “done” because the presentation is scheduled.

## Public-release go/no-go

- [ ] Candidate commit is reviewed, licensed, and reproducibly builds.
- [ ] A newcomer can follow the docs from clean download to install, run, build,
  and test without relying on private knowledge or local caches.
- [ ] The package artifact contains the model, static UI, locale data, and notices,
  and was installed/launched in a clean environment.
- [ ] Backend and frontend verification are green, or known failures are
  explicitly accepted and excluded from claims.
- [ ] Public photos/sample records are permission-cleared; no generated results,
  local application data, keys, or unintended artifacts are included.
- [ ] Documentation accurately states platform support, OCR limitations, local
  storage/privacy boundaries, export compatibility, and recovery steps.
