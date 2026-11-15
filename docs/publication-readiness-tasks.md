# Public source publication: ordered task list

Goal: publish a repository that people can download, understand, install, build,
run, and test. This is a source-code release plan, not a promise of a signed
desktop installer. Do the documentation pass first, then use its exact commands
as the acceptance criteria for clean-environment testing.

## 1. Documentation first — start here

- [x] **Reconcile the install guide with the actual setup scripts.** Review
  [`README.md`](../README.md), [`setup.sh`](../setup.sh),
  [`requirements.txt`](../requirements.txt), `requirements.lock`,
  [`pyproject.toml`](../pyproject.toml), `frontend/package.json`, and
  [`scripts/fetch_model.py`](../scripts/fetch_model.py) together. Keep one
  canonical, copy/paste path for a fresh source checkout.
- [x] **Document prerequisites precisely.** The README records the verified
  Ubuntu 26.04/Python 3.14/Node 22/npm/Chromium versions and example Ubuntu
  package names, and does not claim Windows/macOS or other Python versions.
- [ ] Rehearse the Ubuntu package-install commands on a clean OS image before
  advertising them as tested instructions. The current host was Ubuntu 26.04.1;
  package names were checked, but installation was not tested on a fresh OS.
- [x] **Explain network and model behavior.** `setup.sh` installs Python/npm
  dependencies. The pinned DE·HTR assets are in the source/package and are
  checksum-checked; absent or invalid assets are fetched from the pinned
  Hugging Face revision. Document when internet is needed, model size/disk needs,
  and how to verify the assets without downloading (`fetch_model.py --check`).
- [x] **Separate source setup from end-user package installation.** The README
  documents source setup with `./setup.sh`, wheel build/install smoke testing,
  disposable data, and browser launch. The initial public deliverable is source
  code; a wheel can be built, but no prebuilt desktop installer is promised.
- [x] **Document build and test commands with expected outcomes.** README
  includes backend/frontend tests, typecheck, frontend build, sdist/wheel build,
  and wheel-install smoke-test commands. The latest verified outcomes are
  368 Python and 47 frontend tests; frontend assets are committed with source.
- [x] **Make the architecture guide navigable from the README.** Its component
  diagram and module names match current code; it explains request flow,
  recognition/review, SQLite/image storage, export, migration, and privacy
  boundaries. README links to it and subsystem docs.
- [x] **Add troubleshooting and limitations.** README covers setup/network/model errors,
  camera permissions, browser launch and port behavior, application-data path,
  database backup/migration, build warnings, and manual review when OCR/alignment
  is uncertain. Historical OCR summaries are identified as development-set only.
- [x] **Check documentation links and executable instructions.** Local links were
  checked; setup/tests were run from the source archive, README build/install
  steps were rehearsed in a clean temporary copy, and stale result links removed.

### Documentation baseline found in this review

- The README already has source setup/run instructions, Python and frontend test
  commands, a frontend build command, data location/migration notes, and links to
  [`architecture.md`](architecture.md).
- The README now clarifies that `setup.sh` always requires Node/npm, that setup
  needs dependency access, the model repair behavior, and a source-package build
  example. `setup.sh` and all 368 backend tests also passed from an extracted
  source archive without Git metadata; the workflow evaluator records Git fields
  as null in that case.
- Remaining documentation follow-up: rehearse the Ubuntu apt/Snap package
  commands on a clean OS image; other platforms remain explicitly unverified.

## 2. Public-use rights and data review

- [x] Choose and add a top-level project license. MIT is selected in `LICENSE`
  and declared in `pyproject.toml`.
  Third-party notices do not license the project itself.
- [x] Owner confirmed the copyright-holder text `StartkartenLeser contributors`
  in `LICENSE`.
- [x] Inspect existing redistribution notices for the DE·HTR model and training
  data, Python dependencies, and frontend dependencies. The frontend license
  bundle matches the installed production dependency closure.
- [x] Build source archive/wheel in a clean temporary copy. Confirmed `LICENSE`,
  model notices, Python/frontend licenses, docs, and all 16 photos are included;
  generated test results are excluded.
- [x] Owner confirmed the latest 16 reference photos and sample records are
  fictional, contain no real people, and are cleared for public distribution.
  This status is stated in the README and reference-data docs.
- [x] Owner confirmed the form mockups/PDFs and remaining design materials are
  project-created and cleared to publish.

## 3. Repository and security hygiene

- [x] Review current tracked files: only the latest 16 photos are fixtures;
  generated results are deleted and `tests/results/` is ignored.
- [x] Run targeted secret/key pattern scans on the working tree and textual Git
  history; no high-confidence matches. This does not inspect arbitrary binary
  data or detect every secret format.
- [x] Confirm result outputs remain ignored and docs have no stale result links.
- [x] Inspect sdist/wheel contents: code, model, UI, locale, docs, licenses and
  tests are included; result artifacts and local environments are excluded.

- [x] Rewrite `main` as a clean public baseline so earlier result CSVs, old photo
  versions and `Agent host session` checkpoint commits are not ancestors of the
  public branch. Other local branches remain untouched; publish only `main`.

## 4. Clean-environment verification

- [x] Downloaded source archive (no `.git` metadata), ran `setup.sh`, then ran
  the Python suite without an existing virtual environment or `node_modules`.
  Repeated with pip/npm caches disabled: setup and 368 Python tests passed.
- [x] Backend suite passes (**368 tests**); TypeScript check passed previously.
- [x] Exact README sdist/wheel recipe in a clean copy; wheel installed in a fresh
  Python 3.14 Linux venv and served HTML/JS/CSS.
- [x] Frontend suite now passes: **47 tests** after setting Vitest's timeout to
  20 seconds for slow jsdom/MUI cases. The Enter/autosave behavior passes; no app
  code change was required for this report.
- [x] Exact wheel-build recipe and uncached setup environment checked.
- [x] Run local OCR against the current development photos using bundled model;
  144 observations were produced with 16/16 alignment. A separate one-line wheel
  inference also completed. This is not a holdout accuracy claim; CSV output was
  kept outside the repository.
- [x] Run a real one-line recognition call through the clean wheel install; it
  loaded the bundled model and returned a completed candidate.
- [ ] Smoke-test real camera capture, upload fallback, OCR/manual review,
  autosave, approval, deletion, and CSV export on the declared browser/OS.
- [x] CI is not required for this publication pass; defer it for now. If added
  later, have it run the documented test/build commands and only claim platforms
  represented in its tested matrix.

## 5. Release and maintenance

- [x] Initial artifact plan is source repository/source archive only; the README
  documents how users can build a wheel themselves. No desktop installer is
  planned for this first publication.
- [ ] Publish a changelog/release note with install instructions, known limits,
  model/data licensing, and the tested platform matrix.
- [ ] Re-run the documentation and clean-install checklist for each public
  release; assign an owner for issues, dependency updates, and license review.

## Challenge the plan

- A repository that passes tests is not necessarily installable: packaging can
  omit model/static assets or depend on a developer's existing caches.
- A source download is not a desktop installer. Be explicit about what a user
  must install and whether Node is only setup-time or needed at runtime.
- “Local OCR” does not mean encrypted data. Explain local storage, exported CSVs,
  backups, retention, and deletion accurately.
- Historical scores are not an independent accuracy guarantee. Result files and
  old photos are absent from the current revision, but remain in prior Git history
  unless the public history is cleaned; narrative summaries remain in docs.
- A license decision and permission to publish photos are release gates, not
  details to defer until after the repository is public. MIT is selected and
  the owner has confirmed the test photos are fictional and public-safe.
