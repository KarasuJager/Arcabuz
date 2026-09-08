# Future V2 desktop architecture

No desktop UI is implemented in V1. A future desktop shell must reuse the same core services
as the CLI; it must not maintain another scoring, normalization, or parser implementation.

```text
CLI renderer                         Future desktop shell
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

A desktop shell should run refresh/watch in a worker, use a cancellation event, and marshal
callbacks onto its UI thread. The worker owns the investigation instance: it is not designed
for concurrent mutation by multiple UI threads. Selection, search, and sort state belong
in the view. Evidence, scopes, scoring, and suppression decisions remain in the shared core.

Use the documented schema when persisting or transferring report snapshots. UI annotations
should be separate user data referencing candidate/source IDs, not changes to raw captures.
Copy-to-clipboard and manual external-tool navigation, if added later, need explicit user
actions. A GUI must not replay HAR traffic, fetch imported URLs, or launch target scans.

Before a V2 implementation, test CLI and GUI adapters against identical fixture Reports.
Any new analysis capability goes into the shared package with regression tests first.
