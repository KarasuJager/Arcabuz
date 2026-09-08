# Changelog

## 1.0.0 — 2026-09-08

FuzzRank V1 is defined as deterministic offline fuzzing triage.

- Import HAR 1.1/1.2 metadata, text/base64 bodies, repeated headers, and baseline tags.
- Combine files and directories with format detection, scope filtering, and source provenance.
- Watch local changes with debounce, last-usable snapshots, stale diagnostics, and immutable history.
- Expose configurable input limits, record-level diagnostics, shared body/fingerprint storage,
  bounded shingle sampling, and incremental JSON/HTML writing.
- Add an offline HTML investigation queue with filters, cluster browsing, detail panels,
  baseline support, provenance, and export metadata.
- Document the additive V1 JSON contract and ship its schema in the package.
- Improve version diagnostics, synthetic format coverage, stress tests, and contributor guidance.
- Document the future GUI boundary around the shared investigation service.
- Preserve the original 143 tests; the expanded suite passes 226 tests.

## 0.1.0 — offline foundation

- Native ffuf, feroxbuster, and limited Gobuster imports.
- Evidence bundles, normalization, baseline comparison, exact-body clusters, cross-engine
  deduplication, YAML rules/profiles, terminal/JSON/HTML reports, and a closed local demo.
- Strict duplicate-key validation, bounded imports, partial-result preservation,
  diagnostics, and 143 regression tests before the V1 continuation.
