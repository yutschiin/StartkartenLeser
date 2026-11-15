# UI alternatives for the keyboard-first Wettkampf workflow

- **Status:** Decision superseded by successful local-browser spike: React/Material UI + Python accepted
- **Research date:** 2026-11-10
- **Inputs:** [Workflow contract](keyboard-first-workflow.md),
  [data model](wettkampf-data-model.md), official documentation below
- **Not performed:** Hardware tests, packaged builds, visual prototypes or inspection
  of the existing pywebview exploration branch

The comparison below records the original research, not the current choice.
The Qt and browser spikes are preserved on separate branches. After real-camera
browser validation, the user selected browser/Python with actual Material UI.
See [ADR-0007](../adr/ADR-0007-local-browser-mui.md) and the
[implementation plan](browser-mui-implementation.md).

## 1. What must drive the choice

All five options can make a modern-looking form. None automatically guarantees
a fast or accessible keyboard workflow. Evaluate predictable focus, one-frame
capture, editable OCR, durable approval, immediate return to camera-ready,
offline operation and deployment before visual polish.

Keep the existing Python OCR/domain/persistence core in every option. Rewriting
it in JavaScript or Rust is not needed. Keep German keyed localization, local
image retention and replaceable recognition adapters.

The current first-target documentation is Linux. Windows is considered below
as a possible release target, not an already agreed requirement.

## 2. Comparison

This table is an engineering assessment, not benchmark results or a scored
claim that one toolkit is intrinsically more accessible.

| Option | Keyboard and modern presentation | Camera and Python integration | Distribution and maintenance | Fit here |
|---|---|---|---|---|
| **Qt / PySide6** | Explicit widget focus/tab order, shortcuts and accessibility support. Widgets can look clean and contemporary with deliberate spacing/typography; Qt Quick/QML offers more visual freedom but adds another UI language. | Python calls existing use cases directly. Qt Multimedia offers camera/still-capture APIs and permissions handling; actual backend/device compatibility still needs testing. | Bundle Python, Qt plugins, multimedia dependencies and OCR model; build/test on each target OS. Track Qt/PySide updates and distribution terms. | **Leading desktop candidate:** least architectural change to Python and a natural form/focus model. |
| **Local browser page + Python backend** | Semantic HTML/CSS supports polished forms and standard keyboard navigation. Explicit focus management needed; browser shortcuts/tabs can interfere. | Browser `getUserMedia` captures frames; send only to a loopback Python service. Existing backend stays local. | No embedded browser to ship, but still package/start/stop Python and depend on a supported installed browser. Browser updates are external; backend/frontend updates remain ours. | **Leading web candidate:** good if a browser window and local-service lifecycle are acceptable. |
| **Electron + Python** | HTML/CSS UI in a bundled Chromium version; desktop window/menu control. Same focus/ARIA work as a browser page. | Chromium camera API plus host permission handling. Python is a separate packaged process behind a narrow IPC/local-service boundary. | Ship Chromium, Node, Python and model. Largest duplicated runtime stack qualitatively; sizes need measurement. App releases must carry Electron security updates. | Viable when consistent Chromium behavior and web expertise outweigh runtime/update cost. |
| **Tauri + Python sidecar** | HTML/CSS in a platform webview. Focus/accessibility behavior must be tested on each engine. | Official sidecar mechanism supports packaged Python. Adds Rust host/tooling and process protocol; webview camera permissions vary by platform. | No bundled Chromium, but Python/model still contribute size. Linux webview dependencies and Windows WebView2 provisioning/update strategy matter. | Attractive native web shell if smaller shell size justifies the extra integration surface. |
| **pywebview + Python** | HTML/CSS in an embedded webview with renderer-dependent behavior. Good styling freedom; same keyboard/accessibility obligations. | Direct JS-to-Python API bridge avoids a separate Python sidecar. Camera can be webview-based or a Python camera adapter with preview transport. | Python-friendly, but chosen renderer/native libraries still need packaging. A Qt backend can bring Qt obligations/dependencies back in. | Strong lightweight web-shell alternative; actual renderer/camera behavior is a selection gate. |

### Camera architecture is a separate decision

Do not equate “web UI” with “camera must be owned by JavaScript.”

- **UI-owned camera:** Qt Multimedia or browser/webview capture produces an
  accepted frame for the shared Python image/draft pipeline.
- **Python-owned camera:** a native camera adapter produces frames and exposes
  a bounded preview to the UI. This can avoid embedded-webview camera limitations,
  but adds preview transport, device lifecycle and potentially encoding overhead.

Prefer the simplest working route in the chosen toolkit. Measure real still
resolution and focus/exposure behavior: a webcam's video frame capture is not
automatically equivalent to a full-resolution photographic still.
Request camera access only for scanning; do not request microphone access.

## 3. Important qualifications and obligations

### Qt / PySide6

Qt has documented accessibility and Multimedia APIs [1–3]. That is evidence of
capability, not proof this camera works reliably on Linux or Windows. Custom
painted controls need additional accessibility work; start with standard widgets.
Qt Widgets is the lower-complexity prototype here; consider QML only if a real
visual requirement cannot be met without it.

Qt/PySide are available under commercial and open-source terms [4]. LGPL/GPL
module distinctions and third-party notices must be checked for the exact shipped
components. Dynamic linking alone is not the whole LGPL compliance checklist:
review notices, license/source obligations, replacement/relinking rights and any
installation-information requirements. Do not promise that every module is LGPL
or that a frozen executable is compliant without reviewing its packaging.
Legal review is a release gate, not a reason to reject Qt automatically.

### Browser, Electron and embedded webviews

`getUserMedia` requires permission and a secure context [5]. MDN explicitly
includes loopback origins such as localhost/127.0.0.1 as potentially trustworthy
[6]; this does **not** make an arbitrary HTTP LAN deployment camera-ready.
Test the exact launch origin and browser. Package assets locally; no CDN,
hosted fonts, analytics or remote OCR.

A local service is not automatically private just because it has no cloud.
Bind only to loopback, restrict origins/hosts, protect state-changing requests,
and define ownership/shutdown of the backend. Expose narrow operations, not
arbitrary files or Python execution. Electron must isolate renderer privileges
and expose a minimal bridge [7]. Equivalent care applies to pywebview APIs and
Tauri capabilities.

Electron officially supports its latest three stable major releases and currently
documents an eight-week major cadence [8]. This creates an ongoing upgrade duty,
not a claim that one must rebuild exactly every eight weeks regardless of patch
availability. Bundled Chromium reduces renderer-version variability, but cannot
guarantee device/driver reliability.

Tauri uses platform webviews [9], and documents Python-compatible sidecars [10].
pywebview offers multiple renderers and a direct Python bridge [11–12]. System
webviews reduce bundled engine weight but shift update/provisioning dependencies
to the host. They do not eliminate application security maintenance.

Historical webview camera issue reports are reasons to test, not evidence that
current versions cannot capture. Likewise a WebKit property introduced in a
particular version does not establish when all camera support began. No option
is rejected here using either inference.

### Packaging and licenses across options

PyInstaller is not a cross-compiler [13]. Packaging the existing ONNX/OpenCV
dependencies and model remains necessary with every UI. Test on clean target
machines; development-machine success is insufficient. Offline installation
must provision the renderer/runtime rather than assume it can download at launch.

Electron (MIT), Tauri (MIT/Apache-2.0) and pywebview (BSD-3-Clause) have permissive
top-level licenses [14–16], but those do not replace the obligations of Chromium,
native webviews, plugins, Qt backends or the existing OCR dependencies. Review
the exact distribution and notices regardless of UI choice.

## 4. Provisional recommendation

**Prototype PySide6/Qt Widgets first.** It keeps the application Python-native,
supports direct keyboard/focus control and provides a camera API without adding
a browser service or sidecar protocol. A thoughtfully designed Qt UI need not
look like the existing Tkinter prototype. This is a risk/complexity recommendation,
not a final visual or performance verdict.

**If HTML/CSS styling is the stronger priority, compare a local browser UI next.**
It is the clearest web architecture without immediately adding a desktop shell.
If a standalone window is mandatory, evaluate pywebview's actual target renderer
against the same camera/focus gates before adding Electron or Tauri complexity.
The existing exploration can later be inspected for reusable evidence; it has
not been treated as a successful prototype here.

Choose **Electron** deliberately for controlled Chromium/desktop integration,
or **Tauri** deliberately for a system-webview shell with a supported sidecar.
Neither is necessary solely to get a modern form.

## 5. Prototype and decision gate

The user selected a **Qt/PySide spike**; see the
[bounded spike plan](qt-pyside-workflow-spike.md). Production UI selection remains
open pending its results. The prototype covers Wettkampf header, live preview,
Space capture, immediate entry with Retake focused, gender review, autosave and
Ctrl+Enter approval/return. Use fake OCR to isolate UI timing, then plug in the
existing local pipeline. Do not build several production front ends.

Run the complete [workflow acceptance set K01–K16](keyboard-first-workflow.md#7-measurable-acceptance-scenarios),
including 20 pointer-free cards, backward traversal, key-repeat guards, errors,
restart and packaged offline operation. Also verify:

- Real camera enumeration, required image resolution, permission denial,
  disconnect/reconnect and release on close on each agreed release OS.
- Screen-reader label/value announcements, visible focus, dialogs and 200% text.
- No remote asset requests and no unexpected network listener/exposed API.
- Startup time, peak memory, packaged size and median/p95 cycle timings measured
  on the same machine/fixtures; include approval-to-ready p95 target of 500 ms.
- Reproducible target-OS installation and inventory of licenses/native dependencies.

If Qt passes, record the UI decision in a new ADR and proceed. If it fails, name
the failed requirement and test the web runner-up against that requirement
before switching. Do not decide by screenshots or by an unmeasured size claim.

## 6. Sources and research limits

Official documentation consulted by the research task; loopback, Electron cadence,
Tauri sidecars and pywebview bridge were additionally fetched during synthesis.
Qt documentation could not be re-fetched during synthesis because of a transport
failure; Qt licensing and deployment details remain explicit release checks.
No hardware/performance or current-package compatibility claims were verified.

1. [Qt accessibility](https://doc.qt.io/qt-6/accessible.html)
2. [Accessible Qt widgets](https://doc.qt.io/qt-6/accessible-qwidget.html)
3. [Qt Multimedia](https://doc.qt.io/qt-6/qtmultimedia-index.html) and [permissions](https://doc.qt.io/qt-6/qpermission.html)
4. [Qt licensing](https://doc.qt.io/qt-6/licensing.html) and [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html)
5. [MDN: getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
6. [MDN: secure contexts and trustworthy origins](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts)
7. [Electron security recommendations](https://www.electronjs.org/docs/latest/tutorial/security)
8. [Electron releases and version support](https://www.electronjs.org/docs/latest/tutorial/electron-timelines)
9. [Tauri architecture](https://v2.tauri.app/concept/architecture/)
10. [Tauri sidecars](https://v2.tauri.app/develop/sidecar/)
11. [pywebview usage and JS/Python bridge](https://pywebview.flowrl.com/guide/usage.html)
12. [pywebview installation/renderers](https://pywebview.flowrl.com/guide/installation.html)
13. [PyInstaller platform support](https://pyinstaller.org/en/stable/)
14. [Electron license](https://github.com/electron/electron/blob/main/LICENSE)
15. [Tauri licenses](https://github.com/tauri-apps/tauri#license)
16. [pywebview license](https://github.com/r0x0r/pywebview/blob/master/LICENSE)
