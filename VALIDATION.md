# Engineering validation — 2026-09-08

This record covers **FuzzRank V1 offline triage**, the accepted product scope.
The original 143 tests were retained. No arbitrary-target orchestration is part of V1.

## Environment and automated checks

Local environment: Windows, Python **3.12.13**. Full suite: **226 passed** (final
production-code run: 32.07 seconds). Ruff lint and formatting passed; `pip check`
reported no broken requirements. The wheel and source archive built successfully, and
a wheel installed into a fresh virtual environment passed help, version, doctor,
directory/HAR analysis, watch, local demo, JSON/HTML generation, package-resource
loading, and dependency consistency.

Python 3.11–3.14 on Windows/Linux are configured in GitHub Actions. **Remote CI was not
executed here**; this record verifies the local environment, not every matrix entry.

Executed commands included the following, using the repository virtual environment
(the final distribution and wheel checks use the 1.0.0 package):

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
.venv\Scripts\fuzzrank.exe --help
.venv\Scripts\fuzzrank.exe --version
.venv\Scripts\fuzzrank.exe doctor --json
.venv\Scripts\fuzzrank.exe analyze tests/fixtures --target https://fixture.example --output results/v1-offline/directory --top 3
.venv\Scripts\fuzzrank.exe demo --output results/v1-offline/demo --top 5
.venv\Scripts\fuzzrank.exe analyze results/v1-offline/demo/demo-evidence.json --baseline results/v1-offline/demo/demo-baseline.json --output results/v1-offline/reanalysis --quiet
.venv\Scripts\python.exe scripts/benchmark.py --records 20000 --output results/v1-offline/stress-20000
.venv\Scripts\fuzzrank.exe analyze results/v1-offline/stress-20000/synthetic.ndjson --output results/v1-offline/stress-untraced --quiet
.venv\Scripts\python.exe scripts/browser_smoke.py results/v1-offline/browser-input/report.html --output results/v1-offline/browser-verified
.venv\Scripts\python.exe -m build --no-isolation --outdir results/v1-offline/dist
.venv\Scripts\python.exe scripts/wheel_smoke.py --wheel-dir results/v1-offline/packages --output results/v1-offline/wheel
```

Build isolation was unnecessary because the declared build backend was installed locally.
Workspace copies of build artifacts were used for wheel installation because temporary
build-file permissions differed between local execution identities. No system configuration
or unrelated project files were changed. Failed initial checks were fixed and rerun.

## Local integration

The loopback demo made **47 requests**: 12 baseline captures and 35 discoveries.
It suppressed **22** endpoints and retained **13**:
3 inspect-now, 1 high, 2 medium, and 7 low.

Top scores: `/admin/export` 100, `/swagger.json` 100, `/api/users` 90,
`/admin` 80, `/redirect` 63. Wildcard, custom-404, SPA, duplicate, static,
auth-boundary, and redirect cases are covered. All suppressed observations remain
in reports and checkpointed evidence. Reanalyzing the demo captures reproduced the
same IDs, ordering, scores, baseline labels, and suppression decisions.

Directory analysis of the complete fixture folder produced **22 valid observations**,
**2 excluded origins**, **14 merged repeated observations**, and **6 candidates**.
The API-users candidate preserves ffuf, feroxbuster, Gobuster, and HAR provenance.
The focused three-engine fixture test separately verifies 7 observations becoming
3 candidates with 4 merges. Body-free summaries do not receive fabricated fingerprints.

HAR tests cover versions 1.1/1.2, Unicode text, base64 binary data, omitted content,
redirects, duplicate headers, malformed entries, invalid versions/encodings, baseline
tags, truncation markers, and scope exclusion. Socket and DNS access are forbidden in
offline integration tests.

## Watch validation

Tests modify real local fixture files across **four published generations**:
valid initial data, an incomplete replacement retaining stale evidence, a repaired
replacement becoming current, and deletion removing the current candidate. All earlier
generations and archived bytes remain readable. Separate tests cover debounce,
unchanged inputs, baseline updates, scope locking, mixed good/malformed sources,
report-selection modes, output-write failure, and cancellation.

A simulated Ctrl+C through the actual CLI path returns 130 after a completed snapshot.
A stop event shuts down the polling loop and its test writer joins cleanly. Watch launches
no fuzzer subprocesses. Installed-wheel watch also published a real bounded fixture update.

## HTML and JSON verification

JSON Schema 2020-12 validation runs offline against actual complete and partial reports.
Tests verify stable repeated serialization, legacy field types, body hashes, provenance,
score arithmetic, and additive unknown fields. Failed atomic writes preserve the old file.

An isolated installed Edge browser opened the generated HTML directly as a **file URL**.
Text, priority, status, engine, content-type, noise, cluster, reset, and endpoint-detail
controls passed. The phone-width layout passed after an overflow fix. The browser recorded
**zero JavaScript errors and zero external requests**. Desktop/mobile screenshots and
machine-readable results are in `results/v1-offline/browser-verified/`.
The regular suite also checks escaping and CSP hashes.

## Measured scale

Synthetic repeated-body input, with two observations per endpoint:

| Measurement | 20,000 observations / 10,000 endpoints |
| --- | --- |
| Input bytes | 4,837,780 |
| Analysis with allocation tracing enabled | 53.323 seconds |
| JSON writing with tracing | 40.430 seconds |
| HTML writing with tracing | 7.206 seconds |
| Total with tracing | 100.959 seconds |
| Peak traced Python allocations | 26.12 MiB |
| Separate end-to-end CLI run without tracing | 25.393 seconds |
| JSON size | 42,945,706 bytes |
| HTML size at measurement | 20,095,047 bytes |
| Distinct fingerprints computed | 1 |
| Cross-source observations merged | 10,000 |
| Suppressed duplicate endpoints | 9,999 |
| Retained representative | 1 |

Tracing materially affects time; this is a reproducible local measurement, not a throughput
guarantee. Traced allocations are **not process RSS**. Dataset creation occurs before tracing.
An earlier 5,000-record run and the first 20,000-record run exposed an unnecessary 64 MiB
read allocation; bounded chunk reads reduced the measured 20,000-record peak to 26.12 MiB.
The final cluster-display polish adds a small amount to HTML output size.

Automated stress tests also cover 20,000 body-bearing records, shared byte identity,
cross-source deduplication, bounded fingerprint caching, exact bottom-shingle sampling,
and 10,000 JSONL records with an embedded malformed record. Different/large body-heavy
datasets can consume substantially more memory and time. No arbitrary-scale claim is made.

## Release audit and genuine limits

Release-source and package-content checks found no prohibited project/company identifiers,
hardcoded personal home paths, private-key markers, or common service-token signatures.
Only Rich and PyYAML are declared runtime dependencies; no inference or remote-analysis
dependency is present. Source archives, local reports, virtual environments, and generated
validation artifacts are excluded from Git and distribution packages.

This is a bounded source/package audit, not a claim that arbitrary operator-supplied
captures are safe to publish. Original evidence is deliberately unredacted. No files
were published, and no final software license was selected.

All three optional fuzzer binaries and SecLists were absent. **Real fuzzing binaries
executed: none.** Native compatibility is verified with synthetic format fixtures;
executing fuzzers is outside the accepted offline V1 scope.

Remaining limits: in-memory HAR/JSON-envelope parsing and analysis; full recomputation on
watch updates; growing watch history without pruning; metadata-based change detection;
large browser DOMs for large HTML reports; limited Gobuster saved-dir grammar; body/baseline
availability controlled by capture tools; and no remote CI execution in this session.
