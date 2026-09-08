# Changelog

### 2.0.0 release hardening — 2026-09-09

- Fit tables to available width with optional columns, user-resizable widths, full-value
  tooltips, native full-row inspection, and copy actions that include hidden evidence.
- Remove hidden-page and long-label sizing constraints; balance adjustable candidate
  and detail panels through resize/maximize cycles, including high-DPI desktop layouts.
- Compact identifiers, hashes, media types and timestamps without changing stored data.
- Clarify imported discovery counts, baseline labels, cluster assessments and score caps.
- Refresh candidate details after model resets, preserving a surviving selection and
  clearing obsolete evidence when the selected endpoint disappears or is filtered out.
- Package the approved guardian logo unchanged for the native icon, Home, toolbar and README.
- Add layout, column, copy, label, navigation and asset regressions. Core scoring and the
  JSON/HTML interchange model remain unchanged.

See [final hardening validation](V2_HARDENING.md) for executed checks and visual-review limits.

## 2.0.0 — 2026-09-08

- Add an optional native PySide6 Essentials desktop and `fuzzrank-gui` entry point.
- Reuse the exact V1 investigation, parsers, normalization, baselines, deduplication,
  clustering, YAML scoring, watch publication, and JSON/HTML report services.
- Add asynchronous file/folder/HAR import, source-format preview, scope/profile/baseline
  configuration, input limits, fixed local demo, and safe saved-report reopening.
- Provide native ranked tables, cached sorting/search/filtering, exact score explanations,
  provenance, cluster members, suppressed/noise inspection, baselines, and summary views.
- Expose debounced watch updates, preserved generations, changed filenames, cooperative
  cancellation, safe close, and atomic exports without changing the V1 report schema.
- Add dark/light appearance, keyboard shortcuts, local-only preferences, and drag/drop.
- Preserve all 226 V1 tests; add 56 desktop, parity, corruption, cancellation, and stress tests.
- Extend cross-platform CI and fresh-wheel verification for optional GUI installation.
- Document Qt dependency/license considerations and future standalone packaging boundaries.

See [V2 validation](V2_VALIDATION.md) for executed checks and measured limits. V1's
analysis algorithms are unchanged; only the output-directory helper moved into a shared
module. CLI-only installation continues to work without Qt.

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
