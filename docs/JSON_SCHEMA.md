# FuzzRank V1 JSON report contract

The machine-readable schema is
[`report-v1.schema.json`](../src/fuzzrank/schemas/report-v1.schema.json), shipped as a package
resource at `fuzzrank/schemas/report-v1.schema.json`. It uses JSON Schema 2020-12, only local
definition references, and can be validated offline. Runtime analysis does not need a schema
validator; the development suite uses one for contract tests.

## Identity and evolution

- `format` is `fuzzrank-report`.
- `schema_version` is numeric **1**, preserving the original report's major version.
- `schema_revision` is **1.0.0**, the documented V1 contract revision.
- `metadata` includes tool/version, UTC generation time, schema identifier, and body encoding.

The V1 additions are additive; existing candidate/evidence/scoring fields retain their types.
Readers should require a supported major, ignore unknown properties, and tolerate new reason,
signal, classification, and evidence-quality strings. Additive optional fields and new enum-like
values may arrive in a minor schema revision; corrections that do not change meaning can be
patch revisions. Removing fields, changing types/meanings, or moving inline bodies requires
a new major. A schema document describes its exact revision; a reader may select a newer
schema separately. Tool version and report schema version evolve independently.

## Top-level fields

| Field | Meaning |
| --- | --- |
| `target`, `scope`, `profile` | Canonical target, exact allowed origins, selected profile name |
| `summary` | Nonnegative counts; see equations below |
| `candidates` | All logical endpoints, including suppressed endpoints, in priority order |
| `baselines` | All explicit/tagged baseline observations, including unusable/out-of-scope evidence |
| `excluded` | Out-of-scope discovery observations |
| `clusters` | Membership, representative, counts, characteristics, engines, suppression rationale |
| `configuration` | Exact resolved rule and profile data used |
| `sources` | Manifests for archived source versions participating in the update |
| `partial` | Whether input/limit/capture failures reduced current usable results |
| `warnings`, `import_diagnostics` | Human summaries and complete record-level diagnostics |
| `metadata` | Tool/schema/export details, limits, body-cache count, and watch generation if applicable |

```text
raw_discoveries = out_of_scope + duplicates_merged + unique_endpoints
unique_endpoints = noise_suppressed + unique_candidates
unique_candidates = inspect_now + high + medium + low
```

Raw discoveries count valid observations, including out-of-scope entries; rejected records,
baselines, and recognized non-response events are separate. `requests_made` is 0 for imports
and watch. The fixed local demo records its own request count.

## Candidates and observations

A candidate is grouped by normalized method + canonical URL. Its ID is a stable truncated
SHA-256 of that identity. Query order is preserved; different methods stay separate.
`observations` preserves every parsed source record for the endpoint. `primary` repeats the
selected observation for backward compatibility; it is not additional evidence. `engines`
contains all contributing adapter names, including `har` or evidence-bundle engine names.

Each observation carries method, original URL, status, optional sizes/counts, content type,
redirect, headers, optional capture timestamp/body, truncated flag, source ID, and 1-based
record index. An index identifies a parsed record (nonblank JSONL/text records), not necessarily
a physical line or HAR page number. Unmapped native fields remain in the byte-for-byte archive.

`body` is either `null` (not captured) or `{"encoding":"base64","data":"..."}`. An empty
base64 string is a known empty body, distinct from absent content. Raw fingerprints hash the
decoded imported bytes. Normalized fingerprints hash the conservative normalization result.
HAR text is UTF-8 encoded and identified by `body_source=har-text-utf8`; this is not a guarantee
of original wire-byte identity. Repeated HAR header pairs remain in `header_items`.

`score_reasons` includes signed `points`, `rule_id`, and `reason`; points sum to `score` after
the explicit clamp activation. `baseline` is match/near/different/uncertain/unavailable, with
optional similarity. `evidence_quality` describes support (baseline-compared/body-only/limited),
not a probability. `evidence_gaps` explains missing bodies, incomplete captures, absent reliable
baselines, or conflicting observations. No score is a vulnerability determination.

`suppressed` and `suppression_reason` are conclusions only. Suppressed observations are never
deleted. `response_cluster` joins a cluster; its `members` are candidate IDs and its
`representative` is a member ID. Cluster size counts endpoints; observation_count counts their
original observations. Cluster hashes are deterministic for the current algorithm, not a
promise of identity across future normalization versions.

## Source manifests and watch snapshots

Manifests include opaque source/version `id`, original basename in `original_path`, relative
`archive`, SHA-256, exact byte count, role, status, and format where detected. Absolute source
paths are not exposed in new reports. The source ID incorporates local path identity, so it
can change if an input is moved; candidate IDs do not. Identical file content shares an archive,
while distinct input files retain distinct provenance IDs. An `evidence/*.source.json` sidecar
makes a completed archive attributable even if parsing is interrupted.

Status values include accepted, partial, rejected, stale, removed, limit-excluded, and
ignored-report. A stale manifest identifies the **old** evidence still used. A rejected update
can appear alongside it. A path that cannot be read/archived has a diagnostic, not a fabricated
hash or source archive. Per-record diagnostics have severity/source/message and optional record.
Known non-response events remain in source archives and increment ignored_events.

Resolve `archive` relative to `metadata.evidence_root` from the report's directory. Normal
analysis uses `.`; watch generation reports use `../..`. A standalone copied report remains
readable, but source archives require copying the investigation directory too.

Watch writes `generations/NNNNNN/{report.json,report.html,snapshot.json}`. Requested report files
are complete before `latest.json` advances. The index manifest uses `format=fuzzrank-watch-index`,
generation, summary, source metadata, diagnostics, and relative report paths. It is not itself a
triage report and is not validated by the report schema. Older generations are immutable.

Generation timestamps, source provenance, and local demo port numbers are run-specific.
For reproducibility compare candidate identity, activated rules, scores, clusters, and evidence
hashes. Serializing the same Report instance twice yields identical JSON bytes.
