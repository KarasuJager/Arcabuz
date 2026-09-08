# V2 desktop validation

This is the initial V2 implementation record. See [final hardening](V2_HARDENING.md)
for the later layout, branding, state-refresh fixes and 302-test release validation.

Validated locally on Windows, Python 3.12.13, PySide6 Essentials/Qt 6.11.2, pytest 9.1.1,
and pytest-qt 4.5.0 on 2026-09-08. All testing used synthetic files or the owned loopback
demo. No public target was contacted. Remote CI has been configured, not executed here.

## Tests and checks actually executed

```console
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m build --no-isolation --outdir results/v2-release-dist
.venv\Scripts\python.exe scripts/wheel_smoke.py --wheel-dir results/v2-release-share --output results/v2-release-wheel --gui
.venv\Scripts\python.exe scripts/gui_benchmark.py --records 20000 --output results/v2-final-stress
.venv\Scripts\python.exe scripts/gui_review.py results/v2-dev/demo/report.json --output results/v2-native-review-2
.venv\Scripts\python.exe -m pip install -e ".[dev,gui,gui-test]" --no-deps --no-build-isolation
```

The final full suite passed **282 tests in 39.20 seconds**, with no skips: all **226 V1
tests plus 56 new tests**. Ruff lint and formatting passed. `pip check` passed in both
the development environment and the fresh CLI/GUI wheel environment. Source and wheel
builds succeeded. The release-share directory contains byte-for-byte copies of build
artifacts so the separate installation process can read normal workspace permissions.

The wheel smoke script created a new environment and verified that `fuzzrank` and the
bundled schema came from that environment, not the checkout. It first installed the
CLI-only wheel and confirmed Qt was absent and the missing-GUI diagnostic was useful.
It then installed the GUI extra and launched the installed `fuzzrank-gui` executable
offscreen, loading both Demo and an existing saved report and capturing native PNGs.

Commands executed by that fresh-wheel check:

```console
fuzzrank --help
fuzzrank --version
fuzzrank doctor --json
fuzzrank analyze tests/fixtures --target https://fixture.example --profile api --output analysis --quiet
fuzzrank watch tests/fixtures --target https://fixture.example --max-updates 1 --debounce .05 --poll-interval .05 --output watch --quiet
fuzzrank demo --output demo --quiet
fuzzrank-gui --demo --output gui-demo --settings gui.ini --quit-after-load --screenshot gui-demo.png
fuzzrank-gui --open-report analysis/report.json --settings gui.ini --quit-after-load --screenshot gui-report.png
```

The script resolves fixture and executable paths at runtime; paths above are abbreviated
relative to the repository/output environment. Actual process invocation uses argument
arrays, `shell=False`, and timeouts. GUI startup smoke flags close the window after
successful loading; they do not mock the event loop or worker.

## Functional results

- Fixed loopback demo: **35 discoveries, 22 suppressed endpoints, 13 retained candidates,
  13 clusters, 12 baseline responses**. Bands: **3 inspect now, 1 high, 2 medium, 7 low**.
  Top candidates: `/admin/export` 100, `/swagger.json` 100, `/api/users` 90, `/admin` 80.
  The demo performed its fixed **47 loopback requests** and closed its server.
- Fixture directory: **22 raw observations, 2 out of scope, 14 duplicate observations
  merged, 6 logical in-scope endpoints**. JSON/HAR/ffuf/feroxbuster/Gobuster evidence
  imported together with zero requests. `/api/users` retains four engine provenances.
- GUI watch: real local file updates changed the queue from 3 to 8 observations after
  adding a HAR file. Separate tests wrote malformed intermediate JSON, retained the
  last usable observations with partial diagnostics, then recovered on valid content.
  Start, stop, changed filenames, immutable generations, and latest pointers were checked.
- Parity: identical CLI/GUI inputs produced equal complete candidate serialization,
  summary, and configuration. A spy verified both called `Investigation.refresh()`;
  the GUI call ran on a background thread.
- Exports: GUI JSON matches the shared report model; rebased archive references resolve
  to unchanged original bytes. GUI HTML uses the existing CSP-protected writer. Saved
  reports round-trip all V1 fields without rescoring, with pooled duplicate bodies.
- Robustness: invalid inputs, scope/profile/size errors, corrupt report contracts,
  duplicate keys, invalid bodies, inconsistent references/scores, inaccessible output,
  explicit baselines, scope exclusion, and native literal-text rendering were exercised.
- Cancellation/close: an active core stage was held while GUI heartbeat events continued;
  cancellation preserved the prior view and completed source archives, withheld the new
  report, and waited for worker exit. Closing and preview cancellation were also tested.
- Native models: sort, search, status/band/engine/type filters, selection preservation,
  reasons, clusters, suppressed/static penalties, baselines, provenance, and preferences
  were exercised with pytest-qt. Local imports were tested with network calls forbidden.

Native windows were also launched visibly from the checkout. Actual Home, candidate,
summary, cluster, suppressed, baseline, source, and light-mode screenshots were inspected.
This review led to selected-row contrast fixes, readable placeholders, clearer navigation,
and full-page summary/evidence views. Screenshots stay in ignored result directories because
they include local output paths. This is not a screen-reader or multi-monitor accessibility audit.

## Large native investigation

`scripts/gui_benchmark.py` creates **20,000 distinct endpoints and 20,000 retained rows**,
with mixed statuses, unique response sizes, and deliberately unavailable body evidence.
It performs real shared-core analysis, both report exports, native model population,
search, status filtering, sorting, and selection. A 20,000-row regression also runs in pytest.

Final measured run:

| Operation | Result |
|---|---:|
| Analysis, JSON/HTML writing, and initial GUI display | 11.185 s |
| Text search across 20,000 rows | 0.036 s |
| Status filter | 0.037 s |
| Restore full queue and sort by response size | 0.132 s |
| Select endpoint and populate details | 0.001 s |
| Event-loop heartbeat callbacks during load | 546 |
| Largest measured event-loop callback gap | 0.190 s |
| Native widget count | 275 |

The default Qt comparison loop initially produced a 2.136-second sort and a 3.165-second
event-loop gap. Sorting cached values in Python, with native index remapping, removed
that bottleneck without changing the core. These measurements are one Windows machine,
not latency guarantees, peak memory measurements, or evidence of unlimited scale.
Body-heavy captures, larger reports, and more complex local rules can take longer.

## Repository checks and remaining limits

Git comparison confirmed no modifications to the original analysis algorithms, parser,
profile/rule/schema files, evidence models, or existing V1 tests. Only the output-directory
helper moved from CLI orchestration into shared input utilities. New GUI code adds no
network client, fuzzing process launcher, inference dependency, or imported-data execution.
Source and artifact checks found no prohibited project/corporate references, personal
home paths, or recognizable credential/private-key patterns. Generated captures, local
preferences, environments, and screenshots are excluded from public source artifacts.
Pattern checks are not a substitute for reviewing real engagement evidence before sharing.

Remaining limits: cooperative cancellation finishes the current core stage; analysis is
still bounded and in memory; watch history grows on disk; manual export requires stopping
watch; relocating a report does not copy its archives. No frozen/signed executable has
been built. Windows native/offscreen testing was performed here; Linux and other Python
versions are covered by the configured CI matrix but were not executed in this session.
Qt redistribution obligations and the owner's final project license remain owner decisions.
No package or repository was published.
