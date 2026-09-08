# Desktop guide

## Install and launch

Install `python -m pip install ".[gui]"` from the repository in a Python 3.11+ virtual
environment, then run `fuzzrank-gui`. `python -m fuzzrank.gui` is equivalent and useful
for diagnostics. CLI-only installation continues to use `python -m pip install .`.
Desktop testing additionally requires `.[dev,gui,gui-test]`.

The desktop runs offline on Windows/Linux with native Qt widgets. It neither replays
HAR requests nor starts arbitrary-target fuzzers. **Open demo** creates the existing
fixed loopback demonstration, closes its temporary server, and displays its results.
It needs no external testing tools. `fuzzrank-gui --demo` opens it immediately.

## Analyze evidence

1. Select **Analyze files**, **Analyze folder**, or **Import HAR**. You can drop local
   files/folders onto the window. Mixed compatible input formats are supported.
2. Review detected source formats and sizes. Detection runs in a background worker.
   Unknown/malformed files are reported; partial valid evidence is still usable.
3. Choose `generic`, `web`, `api`, or a custom profile YAML. Optionally supply an exact
   target origin, additional scope file, and explicit baseline evidence. Relative
   Gobuster paths need a target origin. These fields never cause network requests.
   Tagged baseline observations in HAR/bundles remain supported.
4. Choose a new output directory. Nonempty directories are rejected. Recursive
   discovery and input limits use the same V1 protections as the CLI.
5. Start analysis. Progress is stage-based rather than an invented percentage. The
   previous investigation remains intact until a new result is ready.

Defaults: 64 MiB/file, 128 MiB combined, 100,000 observations, 1,000 files. GUI controls
allow safe V1 ranges (up to 256 MiB/file and 512 MiB combined). Responses over the shared
1 MiB body limit use the original parser handling. These are input limits, not total
process-memory guarantees. Analysis and JSON/HAR validation remain in memory where the
core requires it. Split very large investigations.

## Triage

The table defaults to descending priority. Click headers to sort; search paths, hosts,
engines, or score reasons. Combine score-band, status, engine, and content-type filters.
Status/type filters match any observation, while table cells show the primary response.
Filtering/sorting does not rescore or delete evidence.

Default columns fit the available width, giving extra space to paths and content types.
Use **Columns**, or right-click any table header, to show optional fields such as host,
cluster identity, and suppression state. Drag a header divider for a custom width;
**Fit columns to window** restores automatic fitting. Column choices and widths last
for the current session. Showing every field may require horizontal scrolling.

Long identifiers and hashes have compact display values. Hover for the full value,
press **Ctrl+C** to copy the selected cell, or right-click for **View full row** and
**Copy full row with headings**. Full-row actions include hidden columns. Tooltips
are bounded for very large strings; the full-row dialog and clipboard retain the entire
value. Timestamps display seconds in the captured string's timezone; copying
retains the original timezone and precision. No timestamp conversion is performed.
Sources display filenames; their full original paths remain in tooltips and full-row values.

Select a candidate for its full URL, every signed rule activation, response/baseline
metadata, raw/normalized fingerprints, evidence gaps, cluster, and provenance. **Copy
URL** writes only the chosen URL to the clipboard. It does not open it. Resize details
using the horizontal splitter. Text labels distinguish all bands without relying on color.
The splitter keeps the table and details visible and remembers the chosen proportion
while navigating views. A score of 100 can reflect a larger signed rule total capped
by the core; the score note explains that limit and the original cap activation remains
inspectable. The GUI adds no scoring signals.

- **Summary:** imported discoveries, suppressed endpoints, retained queue, score bands,
  clusters, sources, engines, duplicates, excluded observations, and warnings.
  Imported discoveries correspond to `raw_discoveries`, not every request performed by
  an external fuzzer. **Requests made by FuzzRank** shows the separate `requests_made`
  value: zero for offline imports; the fixed loopback demo records its own requests.
- **Clusters:** counts, representative, status distribution, content types, sizes,
  engines, suppression rationale. Double-click or **Open members** to include suppressed
  members. **Reset filters** restores the retained queue.
  Largest endpoint groups appear first, beside the core's existing assessment. The
  selected-cluster panel explains suppression and exposes full identity and provenance.
  A wildcard/custom-404 assessment is shown only when the core supplied it.
- **Suppressed / noise:** suppressed endpoints, baseline/wildcard matches, duplicate
  responses, static-asset penalties, or any negative rule. Penalty filters can include
  retained candidates; a penalty is not the same as suppression.
- **Baselines:** fingerprints, status, size, content type, redirect, completeness, source.
  Missing or unreliable comparison support is explicitly described.
- **Sources:** formats, status, counts, engines, diagnostics, identity, archived SHA-256.
  Up to 500 diagnostics are displayed; all diagnostics, excluded observations, and source
  bytes remain in the standard report and archive.

## Watch local output

Choose **Watch directory**, configure the investigation, then **Start Watching**. Keep
external authorized tools under your own control. FuzzRank only observes local files.
Status shows `WATCHING`, directory and changed filenames; metadata shows last update time.

Debounced changes call the existing V1 service. Malformed intermediate updates retain
last-usable evidence with stale/partial diagnostics. Stable valid updates replace it.
Complete JSON/HTML generations and original source versions remain in the existing V1
directory structure. Generated output is excluded from discovery. Source IDs distinguish
identical basenames; status uses short filenames for readability.

**Stop Watching** waits for a safe boundary and retains the latest view. Stop before
starting another investigation or using manual Export. Every completed watch generation
already contains JSON and HTML reports. History is retained without automatic pruning.

## Open and export

**Open report** accepts FuzzRank schema 1.0.0 JSON, including V1 CLI output. Limits are
256 MiB and 100,000 observations including baselines/excluded records. Invalid schemas,
duplicate keys, broken references, inconsistent score sums and totals are rejected.
Saved conclusions are restored without rescoring. Original 0.1 development reports may
require reanalysis of their evidence.

**Export** uses the existing JSON/HTML writers and atomic replacement. Archive references
are rebased to the destination; archives are not copied or read. For portable evidence,
retain the entire investigation directory. Reports include captured inline bodies but
may refer to archives unavailable after moving them. No archive is fetched on open.

## Keyboard and preferences

| Shortcut | Action |
|---|---|
| Ctrl+O | Choose evidence files |
| Ctrl+F | Open candidates and focus search |
| Ctrl+E | Export current investigation |
| Ctrl+Q | Exit safely |
| Tab / Shift+Tab | Move between controls |
| Arrow keys | Navigate rows |
| Ctrl+C in a table | Copy the selected full cell value |

Preferences: dark/light appearance, default profile, watch debounce (0.05–30 seconds).
They use the local user configuration location through INI QSettings, organization
`FuzzRank`, application `desktop`. `--settings FILE` selects an explicit location.
No evidence paths or recent captures are stored. Filters/sort persist within the session.

## Brand assets

The approved guardian/helmet artwork is preserved in `docs/assets/fuzzrank-logo.png`
and packaged unchanged under `fuzzrank/gui/assets/`. The native window icon and compact
Home/toolbar marks use a viewport of that image. Its navy background is deliberately
retained in both themes. This is an application window icon, not a frozen executable or
installer icon. No new logo or transparent cutout was generated.

## Troubleshooting and limits

- **Dependency missing:** install the `gui` extra into the launcher's environment.
  `python -m fuzzrank.gui` provides console diagnostics. See [dependency notes](GUI_DEPENDENCIES.md).
- **Linux platform plugin error:** run in a desktop session with the libraries required
  by the installed Qt platform plugin. Automated tests use `QT_QPA_PLATFORM=offscreen`;
  this is not a desktop-session substitute.
- **Slow cancellation:** the current core stage finishes safely; evidence stays on disk.
  The application never forcibly kills a thread or clears the previous report.
- **No usable observations:** review source format, scope, diagnostics, and input limits.
  Malformed files within supported-size limits remain archived.
- **Export error:** choose an accessible location. Existing reports and the loaded
  investigation remain intact. Technical details are optional in the error dialog.
- **Large investigations:** native model/view tables were tested with 20,000 observations
  and 20,000 retained rows. This is not unlimited scalability; see [measurements](../V2_VALIDATION.md).

There are no annotations, persistent recent-investigation list, automatic archive
relocation, body rendering, or frozen executable in this release. JSON/HTML interchange
remains the V1 format.

## Screenshot placeholders

Slots for reviewed synthetic-only screenshots: **Home**, **ranked demo with explanations**,
**cluster members**, **watch status**. Actual validation screenshots may contain local paths,
so they remain in ignored result directories and are not automatically published.
