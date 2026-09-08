# FuzzRank V1 offline triage quality gates

**FUZZRANK V1 OFFLINE TRIAGE QUALITY GATES = PASS**

Version **1.0.0** is prepared locally for the accepted offline triage product.
No publication or license selection has been performed. This assessment supersedes the
earlier live-orchestration proposal; arbitrary-target execution is not a V1 requirement.

| Gate | Evidence |
| --- | --- |
| Existing 143 tests preserved; new tests pass | 226 passing tests |
| Lint and formatting | Ruff checks pass |
| Dependency consistency | pip check passes in development and fresh wheel environments |
| Package build | Wheel and source archive build; schema and fixtures included |
| Installed wheel works | Fresh environment, verified package origin and schema resource |
| Help, version, doctor | Executed successfully; optional engine absence handled |
| Analyze, HAR, multiple inputs, directory imports | Local CLI and regression tests pass |
| Watch local fixture changes | Debounce, four-generation recovery/deletion scenario, scope lock, stop/Ctrl+C tests |
| Baseline and wildcard behavior | Demo and explicit/tagged-input tests pass |
| Deduplication and explanations | Cross-engine provenance retained; activation points sum to scores |
| JSON and HTML | Schema/serialization tests, actual reports, browser control checks pass |
| Original evidence preserved | Archive SHA-256/byte comparisons, sidecars, stale/old-generation checks |
| Scalable bounded behavior | 20,000-record measurement, pooled bodies/hashes, bounded shingles, incremental report writing |
| No prohibited analysis dependencies | Runtime manifest and built package inspected |
| No unrelated/private/corporate source material | Release-source and distribution audit found no matches |
| Public repository preparation | README, contribution/security/change docs, CI matrix, license placeholder |
| Shared future GUI boundary | Investigation service and V2 architecture documented; no desktop GUI added |

See [VALIDATION.md](VALIDATION.md) for exact commands, measurements, limitations, and the
scope of the audit. All target interaction was confined to the bundled loopback fixture.
The Windows/Linux Python 3.11–3.14 CI matrix is configured but was not executed remotely.
