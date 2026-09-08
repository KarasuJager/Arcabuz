# V2 final hardening record

Validated on 2026-09-09 on Windows, Python 3.12.13, PySide6 Essentials/Qt 6.11.2,
on the existing `v2-gui` branch. No publication or release tag was created.

**FUZZRANK V2 FINAL HARDENING = PASS** for the checks and local environment below.

## Changes in this pass

| Files | Purpose |
|---|---|
| `src/fuzzrank/gui/window.py` | Balanced panels, two-row filters, clearer labels, cluster assessment, score-cap note, current-snapshot selection, branding |
| `src/fuzzrank/gui/widgets.py` | Visible-page sizing, eliding labels, fitting columns, native copy/full-row actions |
| `src/fuzzrank/gui/models.py` | Compact display formats with unchanged raw values, sorting, and tooltips |
| `src/fuzzrank/gui/presentation.py` | Display-only shortening, escaped tooltips, filename display, largest clusters first |
| `src/fuzzrank/gui/theme.py` | Compact readable spacing and consistent dark/light table backgrounds |
| `src/fuzzrank/gui/brand.py` | Native approved-artwork viewport, badges and window icon, missing-asset fallback |
| `docs/assets/fuzzrank-logo.png`, `src/fuzzrank/gui/assets/fuzzrank-logo.png` | Approved original and byte-identical packaged copy |
| `src/fuzzrank/gui/assets/README.md` | Asset origin and reuse notes |
| `pyproject.toml`, `MANIFEST.in` | Package logo and documentation |
| `tests/gui/test_hardening.py` | 20 new layout, presentation, copy, navigation, selection, and asset regressions |
| `scripts/gui_hardening_review.py` | Visible local walkthrough, assertions, actual-size capture log |
| `scripts/wheel_smoke.py` | Verify installed logo and icon alongside existing CLI/GUI checks |
| `README.md`, `docs/GUI.md`, `CHANGELOG.md`, `V2_VALIDATION.md`, `V2_QUALITY_GATES.md`, this file | Branding, controls, naming, and validation documentation |

Existing uncommitted V2 implementation work was preserved. No V1 analysis, scoring,
parser, rule, profile, evidence-model, clustering, or report-writer algorithm was changed.

## Root causes and fixes

- Fixed column widths wasted expanded space and created unnecessary horizontal scrolling.
  Tables now distribute width across useful text columns, retain compact scalar columns,
  and expose optional fields through column menus. Manual resizing is respected until
  **Fit columns to window**. Sizing visits columns, not every result row.
- Hidden stacked pages and long dynamic strings contributed inappropriate sizing constraints.
  Stacks now size from the visible page; long labels elide without forcing window growth.
  The sidebar remains bounded while content expands. Candidate and detail panes retain
  an adjustable split and minimum useful space. Tighter spacing helps high-DPI desktops.
- Delayed resize/scrollbar layout could momentarily retain oversized columns after maximize.
  Columns fit during resize and settle again after Qt's layout pass.
- Raw identifiers and internal naming obscured useful information. Hashes, cluster/source
  IDs, media types and timestamps have compact displays; original values remain available
  through safe tooltips, full-row inspection, clipboard and existing details/report data.
  Sources show filenames while retaining full original paths.
- Qt model resets do not emit the ordinary row-change signal. A report refresh could leave
  old details visible when the prior endpoint disappeared. Refresh now clears obsolete
  details, preserves a surviving identity, otherwise selects the first visible candidate,
  and shows no stale details when filters yield an empty queue.

Labels include **Imported discoveries**, **Requests made by FuzzRank**, **Response / baseline**,
**Why this score**, **Core assessment**, and **Records**. The summary distinguishes imported
results from requests. Cluster presentation uses only the core's existing conclusions.

Scoring is unchanged. The demo's `/admin/export` has a signed rule total of +110 and the
existing -10 cap activation, producing 100. The GUI explains this cap without adding rules
or duplicating activations. CLI/GUI parity and exact explanation tests pass.

The approved image was not redesigned, regenerated, recolored or overwritten. Native marks
use a viewport of the helmet/chart; the original navy background is retained. Both copies
have SHA-256 `24a65ac9f7d83c54633999db2fd83394aa2c6dc8b7ab8aadf1d814aa41290753`.

## Executed validation

The starting suite passed **282 tests**. The final suite passed **302 tests in 80.95 s**,
with no skips: all existing tests plus 20 new cases. Lint, formatting, development and
fresh-environment dependency checks passed. Editable GUI installation succeeded. Source
and wheel builds succeeded; the installed wheel's CLI and optional GUI passed verification.

```console
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m pip install -e ".[dev,gui,gui-test]" --no-deps --no-build-isolation
.venv\Scripts\python.exe -m build --no-isolation --outdir results/hardening-dist
.venv\Scripts\python.exe -m build --no-isolation --outdir results/hardening-release-dist
.venv\Scripts\python.exe scripts/wheel_smoke.py --wheel-dir results/hardening-dist-share --output results/hardening-wheel --gui
.venv\Scripts\python.exe scripts/gui_hardening_review.py --output results/hardening-native-reviewed
.venv\Scripts\python.exe scripts/gui_review.py results/hardening-native-reviewed/watch/generations/000002/report.json --output results/hardening-source-review
.venv\Scripts\python.exe scripts/gui_benchmark.py --records 20000 --output results/hardening-stress-release
.venv\Scripts\fuzzrank-gui.exe --open-report results/hardening-native-reviewed/export.json --settings results/hardening-editable-gui.ini --quit-after-load --screenshot results/hardening-editable-gui.png
```

Build artifacts were copied byte-for-byte into `hardening-dist-share` to preserve readable
workspace permissions for the separate installation process. The wheel script created a
fresh environment, confirmed imports came from that environment, initially installed only
CLI dependencies, and checked the useful missing-GUI diagnostic. It then installed the GUI
extra, checked the packaged logo/icon, and launched the installed desktop entry point.

It executed `fuzzrank --help`, `--version`, `doctor --json`, directory/HAR `analyze`, bounded
fixture-directory `watch`, and the loopback `demo`. GUI smoke runs loaded Demo and a saved
report offscreen. Separate visible runs used the normal Windows Qt platform plugin.

- Demo: **35 discoveries, 22 suppressed, 13 retained, 13 clusters, 12 baselines**; bands
  **3 inspect now, 1 high, 2 medium, 7 low**. Its fixed owned server handled 47 requests.
- Installed CLI fixture directory: **22 discoveries, 2 outside scope, 14 duplicates merged,
  6 in-scope logical endpoints**, with zero requests. HAR and all engine import fixtures worked.
- GUI watch: adding a local HAR file changed 3 discoveries to 8, retained both source
  provenances, kept the surviving selection current, and stopped cleanly using the toolbar.
- GUI JSON/HTML exports succeeded. JSON reopening retained complete candidate serialization.
  The HTML writer's existing CSP remained present. Archived source SHA-256 values matched
  the original bytes in fresh-wheel analysis/watch outputs.
- Regression coverage includes malformed data, cancellation, scope, empty filtered queues,
  parity, sorting/filtering, copy access, selection changes, cluster navigation and missing assets.

## Visual review and window sizes

The application was launched visibly. Qt drove its real actions, selections, resize events,
and workers; the resulting native window captures were individually visually inspected.
This is an assistant visual review of actual rendered windows, not a human mouse-driven
acceptance session, browser mockup, or pixel-difference test. Native file-picker interaction
was not manually exercised; application import/export workflows and dialogs have automated coverage.

Reviewed Home/logo, Demo, Summary, Candidates restored/maximized/after repeated resizing,
search/reset, selected score explanations, response/baseline details, Clusters, selected
cluster members, Suppressed/noise, Baselines, Sources, light-mode provenance and baselines,
dark-mode restoration, JSON export/reopening, HTML export success, watch start/update/stop,
and real fixture-source filenames and absent-baseline messaging. The stale-detail issue
found in the walkthrough was corrected and the watch captures were re-inspected.

| Qt client size, logical pixels | Candidate viewport, logical pixels | Details height |
|---|---|---:|
| 1280 × 720 | 1046 × 204 | 210 |
| 1366 × 768 | 1132 × 236 | 226 |
| 1600 × 900 | 1366 × 317 | 277 |
| 1920 × 1080 | 1700 × 429 | 345 |
| Native maximized: 1280 × 649 | 1046 × 133 | 210 |

Three maximize/restore cycles were executed. The local screen used **150% scaling**
(device-pixel ratio 1.5), with 1280 × 672 logical pixels of available work area. Larger
client windows were rendered/captured beyond that work area; the physical monitor
resolution was not changed. All requested client sizes were achieved exactly. Major
table views also passed both-theme invariants at these four sizes plus **1280 × 640**.
Default candidate columns had zero horizontal scroll range in the reviewed captures.
At small sizes the detail/table split can be dragged to show more reasons or more rows.

Captures/logs are retained only in ignored `results/` locations because they contain local
paths. No screenshots or investigation evidence were automatically published.

## Large investigation

Final 20,000-observation / 20,000-retained-row run: shared-core analysis, both reports and
initial display **19.515 s**; text search **70 ms**; status filter **69 ms**; sort **208 ms**;
selection **2 ms**. During loading, 949 heartbeat callbacks ran; the largest measured gap
was **349 ms**. Native widget count was **287**, independent of having 20,000 table rows.
These are local measurements, not latency or memory guarantees. The separate full test
suite also exercised its existing 20,000-row case.

## Release boundaries and remaining limits

Source/build-artifact checks found no prohibited project/corporate references, personal
home paths, recognizable credential patterns, or private-key markers. The approved PNG
and packaged copy were checked for forbidden path/name patterns too. Dependency metadata
contains no inference/model/API dependency. No target execution, network client, report
model fork, analysis duplicate, or AI feature was added. Pattern checks do not certify
future imported engagement evidence as safe to publish.

Windows native/offscreen validation was performed here; Linux, other display scales,
multi-monitor movement, and screen-reader behavior were not validated in this pass.
Column preferences last for the session. Showing all optional fields or setting large
manual widths can require horizontal scrolling. Tooltips cap unusually large text at
8,192 characters; full-row inspection/copy retains the full value. The brand retains its
navy background; no transparent variant, frozen installer, signed executable, or final
owner license was created. Existing cooperative cancellation, in-memory limits and watch
history retention remain as documented in the desktop guide.
