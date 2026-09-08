# Contributing

FuzzRank is an offline evidence triage application. Keep analysis deterministic,
explainable, local, and independent from the CLI. Contributions must preserve source
bytes, make malformed inputs visible, and keep supported commands compatible.

## Development

Use Python 3.11+ in a virtual environment:

```console
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
python -m build
```

Tests use synthetic records and the bundled loopback server. Do not introduce tests
that contact public targets. Keep real engagement exports, authentication material,
personal paths, generated reports, and client identifiers outside contributions.
Preserve the [MIT license](LICENSE.md) and applicable third-party notices.

## Add an import format

1. Add `engines/<name>.py` implementing `parse(data, source, target=None) -> ImportResult`.
2. Map native fields through `engines.base.observation()` and `collect()` to keep validation,
   body pooling, record numbering, rejection counts, and diagnostic behavior consistent.
3. Register the adapter and conservative format detection in `engines/__init__.py`.
4. Add synthetic native-shaped fixtures with documented format families. Test malformed,
   incomplete, unsupported, and ambiguous records, method/scope semantics, and provenance.
5. Archive through `InputLoader`; an adapter never rewrites inputs, dereferences body-file
   pointers, fetches a URL, or executes commands embedded in a capture.

Unknown event types should produce a diagnostic. Known non-response events can be counted
as ignored events because their original records remain in the archive. If a parser cannot
recover record boundaries, reject the file clearly instead of inventing observations.

## Add a scoring rule

Copy `src/fuzzrank/rules/default.yaml`, then run with `--rules custom-rules.yaml`.
Rules have unique `id`, integer `points`, nonempty `reason`, and a `when` mapping.
Selectors: `path_tokens`, `extensions`, `content_types`, `statuses`, and `signals`.
Separate selectors are AND; values inside ordinary selectors are OR; named signals
must all be true. Content types accept glob patterns. Path tokens match decoded path
components/tokens, not arbitrary query values. No executable expressions are evaluated.

For example, a rule with `when: {path_tokens: [export]}` can adjust manual-review priority.
Test both activation and non-activation; verify that explanation points sum to the score.
New evidence-derived signals belong in the analysis pipeline and require semantic tests.
Do not label a rule activation as proof of a vulnerability.

## Add a technology profile

Copy a YAML file from `profiles/`. Set its name, description, extension/wordlist hints,
and `rule_points` overrides, then use `--profile ./custom-profile.yaml`.
Unknown rule IDs and invalid weights are rejected. Test the profile with positive and
negative synthetic captures. Profiles must not initiate detection or network requests.

## Report compatibility

Read [the JSON contract](docs/JSON_SCHEMA.md) before changing models. Keep schema tests,
body encoding, provenance, summary arithmetic, and suppression evidence intact.
Do not duplicate analysis inside a report renderer or future UI. Include failure and
interruption tests for changes to imports, watch publication, and atomic output writing.

The CI matrix builds on Windows and Linux with supported Python versions. No package or
repository publishing is configured. Local checks do not imply that remote CI has run.

Optional browser verification: install `playwright` in your development environment and
use an installed Microsoft Edge browser, then run `scripts/browser_smoke.py` against a demo
report with `--output results/browser-check`. This extra driver is not a runtime dependency
or a requirement of the regular pytest suite. The check opens a local file and closes its
isolated browser afterward; screenshots stay in the selected output directory.
