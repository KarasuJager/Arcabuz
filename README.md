# FUZZRANK

<img src="docs/assets/fuzzrank-logo.png" width="420" alt="FuzzRank guardian helmet and ranking emblem">

**Deterministic fuzzing triage for pentesters.**

FuzzRank turns saved discovery results into an explainable investigation queue:

1. Perform authorized fuzzing with your preferred external tools.
2. Import their output, browser HAR captures, or evidence bundles.
3. Normalize responses and merge repeated endpoint observations.
4. Group identical responses and suppress well-supported noise.
5. Apply explicit YAML scoring rules.
6. Inspect the highest-priority candidates in your preferred manual testing tool.

**FuzzRank prioritizes discovered endpoints. It does not claim that a candidate is vulnerable.**

Analysis and watch mode operate on local files. They never replay captured requests,
fetch imported URLs, launch fuzzers, or follow redirects. Analysis uses deterministic
rules and hashes, with no AI, inference models, embeddings, or remote services.
The optional demo creates and closes its own loopback-only test server.

## Install

Python 3.11+ is required. CLI dependencies are Rich and PyYAML. The optional native
desktop interface adds PySide6 Essentials (Qt Widgets) and JSON Schema validation.

```console
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

python -m pip install .
fuzzrank --help
fuzzrank --version
fuzzrank doctor
```

For development, install with `python -m pip install -e ".[dev]"`.
Engine binaries, databases, containers, and background services are unnecessary for imports.
FuzzRank source code is [MIT licensed](LICENSE.md), copyright (c) 2026 KarasuJager.
PySide6 / Qt is an external optional GUI dependency with its own licensing terms;
FuzzRank's MIT license does not relicense Qt or PySide6. See the
[GUI dependency notes](docs/GUI_DEPENDENCIES.md).

## Desktop interface

FuzzRank V2 provides a native Windows/Linux desktop over the same V1 analysis engine.
The CLI remains available independently. Install from this checkout:

```console
python -m pip install ".[gui]"
fuzzrank-gui
fuzzrank-gui --demo
fuzzrank-gui --open-report results/review/report.json
```

Choose **Analyze files**, **Analyze folder**, or **Import HAR**. The configuration window
detects source formats, lets you choose a profile, optional scope/baselines, input limits,
and a new output directory. Analysis runs in the background; the previous investigation
remains available until the new result is ready. Local files/folders can also be dropped
onto the window.

The native candidate table supports score sorting, text search, and priority, status,
engine, content-type, and cluster filters. Selecting a row shows every signed score
activation, response metadata, fingerprints, baseline support, and source provenance.
Dedicated views cover summary metrics, clusters, suppressed/noise results, baselines,
and parsing diagnostics. Open cluster members to include suppressed evidence; reset
filters to return to the retained queue. Drag the horizontal splitter to resize details.

**Watch directory** uses the existing debounce and immutable snapshot service. Watch
status shows the folder, last update, and changed filenames. **Stop Watching** ends the
worker safely. JSON/HTML reports are produced automatically; stop watching before using
the manual **Export** action. Neither interface launches fuzzers or replays captures.

Shortcuts: **Ctrl+O** import, **Ctrl+F** search, **Ctrl+E** export, **Ctrl+Q** exit.
Preferences contain dark/light appearance, default profile, and watch debounce only.
No recent evidence paths or capture contents are stored in preferences.

See the [desktop guide](docs/GUI.md), [shared architecture](docs/V2_GUI.md),
[Qt dependency and redistribution notes](docs/GUI_DEPENDENCIES.md), and
[V2 validation](V2_VALIDATION.md) and [final hardening](V2_HARDENING.md).
The GUI is native and backend-free; it does not use
a browser runtime, remote resources, or an application server.

## Analyze evidence

```console
fuzzrank analyze ffuf.json --output results/review
fuzzrank analyze ffuf.json ferox.jsonl gobuster.txt --target https://fixture.example
fuzzrank analyze captures/ --recursive --profile api --output results/api-review
fuzzrank analyze browser.har --profile web --baseline missing-paths.har
fuzzrank analyze captures/ --format auto --reports html --verbose
fuzzrank analyze ffuf.json --quiet --reports json --output results/automation
```

Inputs can be files, directories, or a mixture. Directory discovery is sorted and checks
`.json`, `.jsonl`, `.ndjson`, `.ejson`, `.har`, `.txt`, and `.log` files by content.
Nested directories require `--recursive`. Hidden files, symlinks, and generated output
directories are not followed; explicit symlinks are rejected. Repeated selections of
the same file are loaded once. Generated reports are recognized by content and skipped
with a diagnostic. Unsupported files with selected extensions produce diagnostics.

Each output directory must be new or empty. Inputs are never modified. Supported-size
inputs are archived before parsing, including malformed files. A partially usable run
produces reports with exit code 3; an analysis with no usable discoveries returns 1.
Malformed JSONL records have individual diagnostics and retain valid neighboring records.
Incomplete JSON arrays cannot be safely reconstructed.

`--format` selects the **input** parser. `--reports both|json|html|none` selects exports;
source archives are written in every mode. `--top 5` to `--top 20` gives a practical
terminal shortlist. `--quiet` hides progress and summaries; errors still reach stderr
and diagnostics remain in report files.

Exit codes: **0** complete, **1** runtime/input error, **2** invalid CLI arguments,
**3** partial results, **130** interruption outside the demo's checkpointed collection.

## Native exports and HAR

| Import | Supported forms | Body evidence |
| --- | --- | --- |
| ffuf | JSON/EJSON results envelopes, JSON arrays, newline-delimited JSON | Normally omitted |
| feroxbuster | Response NDJSON or arrays; recognized non-response events counted separately | Used only when present |
| Gobuster | Saved dir results with status, optional size and redirect | Omitted |
| HAR | HAR 1.1/1.2 entries with text, base64, or omitted response content | Preserved when available |
| Evidence bundle | `fuzzrank-evidence-v1` JSON | UTF-8 text or exact base64 bytes |

For an independently configured, authorized run, select these **export settings** in the
external tool:

| Tool | Output settings |
| --- | --- |
| ffuf | `-of json -o captures/ffuf.json`, or `-of ejson -o captures/ffuf.ejson`; `-json` emits JSONL to stdout |
| feroxbuster | `--json --output captures/ferox.jsonl` |
| Gobuster dir | `-o captures/gobuster.txt` |

These are output-option fragments, not FuzzRank execution commands. Refer to the upstream
[ffuf output options](https://github.com/ffuf/ffuf#usage),
[feroxbuster option definitions](https://github.com/epi052/feroxbuster/blob/main/src/parser.rs),
and [Gobuster output management](https://github.com/OJ/gobuster#-output-management).
Synthetic version-family fixtures cover ffuf 2.x, feroxbuster 2.x, and Gobuster 3.x shapes;
they do not certify every release or build.

Gobuster support is limited to saved directory-result lines, not banners, color escapes,
DNS/vhost output, or arbitrary console text. Relative results require `--target`.
Structured formats take precedence for tools that provide them.

HAR import extracts method, URL, status, content type, size, redirect, timestamp, headers,
and available response bodies. Repeated headers retain every value. Invalid entries,
unsupported encodings, and failed requests with status 0 get diagnostics. HAR request
cookies and bodies stay in the original archive and are never executed.

HAR text is Unicode exported by the capture tool: its raw fingerprint describes the
UTF-8 representation of that text, not necessarily the original network bytes. Base64
content preserves its decoded bytes. Missing bodies remain unknown. Known truncated
captures can use `_truncated: true` on the entry or response content object.
FuzzRank does not infer exact body equality from matching status/length metadata.

## Watch a local results folder

```console
fuzzrank watch captures/ --target https://fixture.example --output results/watch
fuzzrank watch captures/ --recursive --profile api --baseline baselines.har
fuzzrank watch captures/ --debounce 1 --poll-interval 0.5 --reports json
fuzzrank watch tests/fixtures/ --target https://fixture.example --max-updates 1
```

The watcher polls local file metadata, waits for a stable interval, and reloads changed
sources. It never starts a fuzzer. Scope is fixed when explicitly supplied or inferred
from the first usable discovery; replacing input files cannot silently change it.

On a malformed replacement, previously usable observations from that source remain
active and are labeled **stale**. Rejected replacement bytes and diagnostics are archived.
On the first version of a partially parseable file, valid records are retained and the
report is partial. A complete valid replacement becomes current. Deleted sources leave
the current queue but remain in earlier snapshots. A valid empty export is treated as
empty; it cannot be distinguished from an intentional reset.

Every completed update gets an immutable generation directory. `latest.json` changes
only after all requested reports finish. `index.html` links to the most recent HTML;
reload the index to see subsequent updates. Earlier snapshots and source versions stay
available. Ctrl+C exits cleanly and preserves completed artifacts; no child fuzzer exists
to terminate. An interruption can leave an unfinished generation that is not referenced
by the completed pointer.

Polling detects size, modification-time, and inode changes. A producer that preserves
all three may evade change detection. Prefer atomic file replacement. Watch runs rebuild
the investigation when inputs change; they are not an incremental database. History grows
on disk without automatic pruning. Start a new output directory for a new watch session.

## Scope and baselines

Scope matches exact **scheme, hostname, and effective port**. Without `--target`, the
first valid discovery determines it. Prefer an explicit target for mixed-host captures.
`--scope scope.txt` adds exact HTTP(S) origins, one per line; blank lines and comments are
allowed. Wildcards and path-based scope entries are rejected. Excluded observations remain
inspectable in JSON and original archives. Imported redirect destinations are never followed.

`--baseline FILE` is repeatable and accepts any supported input format or directory.
Designate observations collected from independently chosen paths known by the operator
not to exist, under the same request/session conditions as the discoveries. Evidence
bundles can tag individual records with `"baseline": true`; HAR entries can use
`"_fuzzrank_baseline": true`. Explicit baseline selection takes precedence if a file is
also in the discovery folder. Tagged baselines are excluded from discovery counts.

Two **distinct missing paths** must agree on complete normalized body, status, media type,
and redirect before they establish a baseline. The closest matching origin/method/subtree
is used. Body-free exports cannot establish a body baseline. FuzzRank never invents one;
each candidate exposes evidence quality and missing support.

Raw and normalized SHA-256 fingerprints are kept separately. Normalization narrowly
handles labeled timestamps, request IDs, and nonce-like fields; it preserves application
identifiers, reflected paths, and unlabeled volatile-looking text. Original evidence never
changes. Ambiguous JSON or unrecognized encodings use original bytes for comparison.

Exact response clusters use origin, method, status, media type, redirect, and normalized
body hash. Conflicting or incomplete evidence disables automatic body suppression.
Repeated custom-404/wildcard patterns retain a representative. Identical successful
responses also retain their highest-priority representative. Duplicate 401/403 responses
are retained unless they match a confirmed baseline. Approximate baseline similarity
can penalize a score but never suppress a record by itself.

## Scores and profiles

The default starts at 10, adds every activated YAML rule, and clamps to 0–100.
Explanations include the starting score, rule IDs, signed points, and any clamp, so their
sum equals the displayed score.

| Band | Score |
| --- | --- |
| INSPECT NOW | 90–100 |
| HIGH | 70–89 |
| MEDIUM | 40–69 |
| LOW | 0–39 |

Rules cover administrative/internal/debug surfaces, API descriptions, upload/import/export
functionality, authentication boundaries, JSON/XML types, unusual redirects, unique bodies,
rare status/size behavior, static assets, duplicates, and baseline penalties.
A 200 status alone adds no points. A 403 is contextual evidence, not a security defect.

`generic`, `web`, and `api` profiles adjust rule weights and carry optional extension and
wordlist hints. Custom profile and rule YAML files are validated before use.
`doctor` and `wordlists` detect common SecLists directories and `SECLISTS_PATH`;
lists are never downloaded or executed. No large wordlists are bundled.

## Reports and evidence

```text
results/review/
  report.json
  report.html
  sources.json
  evidence/<sha256>.<original-extension>
  evidence/<source-id>.source.json

results/watch/
  latest.json
  index.html
  sources.json
  evidence/...
  generations/000001/report.json
  generations/000001/report.html
  generations/000001/snapshot.json
```

The HTML report provides summary cards, a ranked queue, text search, priority/status/engine/
content-type filters, a noise toggle, a cluster browser, endpoint detail panels, score
explanations, provenance, baseline information, import diagnostics, and export metadata.
Filters combine; status/type filters consider every observation, not only the representative.
Reset clears all filters. Cluster controls reveal their members including suppressed noise.

HTML is standalone and backend-free. It escapes untrusted text, loads no external resources,
uses hashed inline script/style CSP, and never renders captured bodies as HTML.
JavaScript enables filtering; details remain readable without it.

JSON preserves all candidate observations, suppressed and excluded evidence, hashes,
baseline records, activated rules, exact configuration, source manifests, and diagnostics.
The stable contract is [documented here](docs/JSON_SCHEMA.md) and its
[JSON Schema](src/fuzzrank/schemas/report-v1.schema.json) ships in the wheel.
Reanalyze original archives or evidence bundles; generated reports are not parser inputs.

Archive manifests expose the original basename and opaque source ID, not the local absolute
input path. Archive bytes remain unchanged, so any private data already in captures remains
there. Treat reports and archives with the same access controls as source evidence.

## Local example

```console
fuzzrank demo --output results/demo --top 5
```

The fixed loopback fixture covers custom 404s returning 200, ordinary 404s, SPA and wildcard
fallbacks, admin boundaries, API/schema responses, static files, duplicates, and redirects.
It makes at most 47 planned requests to its own temporary listener and closes it afterward.

```text
FUZZRANK SUMMARY
Raw discoveries           35
Noise suppressed          22
Unique candidates         13
Inspect immediately        3
High interest              1
Medium interest            2
Low interest               7

[100] GET /admin/export
[100] GET /swagger.json
[ 90] GET /api/users
[ 80] GET /admin
[ 63] GET /redirect
```

These figures come from the local synthetic scenario, not a public target.

## Limits and troubleshooting

Default limits: **64 MiB per file**, **128 MiB combined**, **100,000 observations including
baselines**, **1,000 files**, and **1 MiB per decoded body**. Adjust with `--max-file-mb`,
`--max-total-mb`, `--max-records`, and `--max-files`. Hard ceilings are 256 MiB/file,
512 MiB combined, 100,000 observations, and 10,000 files.

A file exceeding the per-file cap is not archived or parsed; its untouched original remains
at the supplied path and the diagnostic explains the refusal. Files exceeding aggregate
limits may be archived but excluded from analysis. Record errors retain individual
diagnostics even when terminal warnings are abbreviated.

JSONL is decoded one record at a time. Repeated bodies share byte storage and fingerprints;
baseline samples are bounded; clustering uses hashes rather than pairwise comparisons.
JSON/HTML are written incrementally without first materializing another complete report.
JSON envelopes/HAR and analysis remain in memory. Input caps are not total-memory guarantees.
Exported JSON repeats inline bodies for schema compatibility. Large HTML queues still
consume browser memory. See [measured stress results](VALIDATION.md).

- **No wildcard reduction:** supply complete bodies and two agreeing missing-path baselines.
- **Partial results:** inspect import diagnostics, stale-source status, and archived bytes.
- **Nothing in scope:** check scheme, host, and port; explicit scope does not fetch any URLs.
- **Watch appears idle:** inspect file extension, debounce, parse errors, and output exclusions.
- **Output exists:** choose a new empty directory; existing evidence is not cleared.
- **Optional engine missing/version warning:** imports still work; `doctor` runs bounded
  version checks only. Unsupported version strings are reported without guessing compatibility.
- **Very large captures:** split investigations or select JSON-only output; avoid unnecessary
  body duplication in source exports.

## Architecture and contributing

```text
src/fuzzrank/
  cli.py                     argument handling and terminal orchestration
  gui/                       native models, views, dialogs, and background workers
  inputs.py, service.py      local loading and shared investigation service
  watch.py                   debounce, reload, immutable publication
  models.py, scope.py         evidence/report model and exact-origin scope
  engines/                   ffuf, feroxbuster, Gobuster, HAR, evidence parsers
  analysis/                  normalization, baselines, dedup, clusters, scoring
  pipeline.py                deterministic analysis composition
  reporting/                 Rich, JSON, standalone HTML
  profiles/, rules/, schemas/ versioned data and public contract
tests/                       synthetic fixtures and local integration tests
scripts/                     reproducible local benchmarks and wheel validation
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding a parser, rule, or technology profile,
[SECURITY.md](SECURITY.md) for evidence handling, and [docs/V2_GUI.md](docs/V2_GUI.md)
for the shared-core desktop architecture. See [CHANGELOG.md](CHANGELOG.md),
[V1 quality gates](V1_QUALITY_GATES.md), and [V2 quality gates](V2_QUALITY_GATES.md).

Use only evidence from systems you own or have explicit authorization to assess.
The human tester decides what to investigate.
