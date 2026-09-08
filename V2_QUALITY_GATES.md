# FuzzRank V2 GUI quality gates

This records the initial V2 implementation gates. The subsequent release-hardening pass
passed **302 tests** and is documented in [final hardening validation](V2_HARDENING.md).

**PASS — 2.0.0 native offline desktop over the unchanged V1 analysis core.**
See [executed validation and limitations](V2_VALIDATION.md). Local validation was Windows
Python 3.12.13 / Qt 6.11.2; this does not claim remote CI or Linux execution.

| Gate | Evidence | Result |
|---|---|---|
| 1–2: preserve V1 tests and pass new tests | 226 existing + 56 new = 282 passed, no skips | PASS |
| 3–5: lint, formatting, dependencies | Ruff checks; development and fresh-environment pip check | PASS |
| 6–7: build and fresh installation | Source/wheel build; isolated 2.0.0 wheel verification | PASS |
| 8: CLI compatibility | Installed help, version, doctor, analyze, watch, demo; regression suite | PASS |
| 9–10: installed GUI launch and Demo | Real Qt startup, worker, event loop, demo and PNG capture | PASS |
| 11–13: file/directory/HAR analysis | Native wizard and direct worker fixture workflows | PASS |
| 14: GUI watch | Add/change/partial/recovery, generations, changed file, start/stop | PASS |
| 15: filters and sorting | Table tests and real 20,000-row native benchmark | PASS |
| 16: exact scoring explanations | Signed activation rows match shared Report | PASS |
| 17–19: clusters/noise/baselines | Dedicated view models, member navigation, explicit baseline test | PASS |
| 20–21: JSON/HTML exports | Shared writers, native export action, equality and CSP checks | PASS |
| 22: core parity | Complete CLI/GUI candidate, summary, configuration equality; same service spy | PASS |
| 23: cancellation/state | Responsive cancellation, preview stop, safe close, retained archives/view | PASS |
| 24: large investigation | 20,000 retained rows; 0.036 s search, 0.132 s sort, 0.190 s largest gap | PASS |
| 25–26: deterministic offline boundary | Dependency audit, code review, network-forbidden import test | PASS |
| 27–28: public-source hygiene | Source/artifact pattern checks; generated/private artifacts excluded | PASS |

No publishing or final project-license selection was performed. A future frozen desktop
installer and additional platform/accessibility validation remain separate work.
