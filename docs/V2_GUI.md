# V2 desktop architecture

The optional PySide6 desktop reuses the same core services as the CLI. It has no separate
scoring, normalization, clustering, or parser implementation, and no browser/server runtime.

```text
CLI renderer                         Native desktop shell
     |                                        |
     +------------- Investigation ------------+
                         |
          InputLoader + shared engine parsers
                         |
                pipeline.analyze()
                         |
    normalization / fingerprint cache / deduplication
          baseline index / clusters / YAML rules
                         |
               Observation + Report models
                         |
           JSON / HTML / terminal / UI views
```

`Investigation.refresh()` owns file loading, scope selection, configuration, and analysis.
It returns the same `Report` consumed by CLI renderers. `InputLoader` handles immutable
source archives, last-usable imports, body sharing, limits, and import diagnostics.
`watch.watch()` takes cancellation and report/error callbacks; it does not depend on Rich
or a GUI event loop. `watch.publish()` publishes complete versioned snapshots.

The desktop runs refresh/watch in a QThread worker, uses a cancellation event, and marshals
callbacks onto its UI thread. The worker owns the investigation instance: it is not designed
for concurrent mutation by multiple UI threads. Selection, search, and sort state belong
in the view. Evidence, scopes, scoring, and suppression decisions remain in the shared core.

Use the documented schema when persisting or transferring report snapshots. UI annotations
should be separate user data referencing candidate/source IDs, not changes to raw captures.
Copy-to-clipboard requires an explicit user action. The GUI does not replay HAR traffic,
fetch imported URLs, open external links, or launch target scans.

The mandatory parity test compares full candidate serialization, summary, and configuration
for identical CLI/GUI inputs and verifies calls to the exact same Investigation service.
Any new analysis capability belongs in the shared package with regression tests first.

## Native application boundary

`gui/worker.py` calls the existing investigation, fixed loopback demo, watch, and report
writers. `gui/presentation.py` builds cached display/search values from a shared `Report`;
it aggregates presentation counts and uses the core fingerprint cache for baseline display.
`gui/models.py` sorts cached scalar values and remaps native persistent indexes. It filters
the view only, without changing core candidate order, scores, or suppression. No widget is
created for each endpoint. All Qt model mutations occur in the GUI thread.

`gui/window.py` and `dialogs.py` handle navigation, configuration, literal text, selection,
and worker lifecycle. Preferences use local INI QSettings for appearance, default profile,
and debounce. Evidence paths and recent history are not persisted. Compatible filters,
sort state, and selected candidate IDs survive watch refreshes during the session.

`reporting/load_report.py` restores the existing V1 contract without rescoring. It validates
the bundled schema, bounded bodies, raw hashes, identities, references, summary totals,
and score sums. Archive references remain data and are never automatically read. Unknown
additive model properties are ignored; existing metadata dictionaries are retained.
Opening a saved report does not establish its authenticity. Reimport its original evidence
to perform a new analysis. There is no GUI-specific report schema.

Cancellation is cooperative: the current core stage completes, completed archives/atomic
reports remain intact, and a cancelled result does not replace the prior view. Window close
requests cancellation and waits asynchronously for worker exit. No forced QThread termination
is used. Very large parse or analysis stages can delay the actual stop while the UI remains
responsive. Watch generations use the same immutable publication behavior as the CLI.

The only V1 orchestration refactor moves `prepare_output()` from `cli.py` to `inputs.py`;
the CLI still imports it for compatibility. Analysis algorithms are unchanged.
