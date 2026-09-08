"""Escaped static HTML with local-only search; response bodies are never rendered."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path

from fuzzrank.analysis.fingerprint import FingerprintCache
from fuzzrank.models import Candidate, Report
from fuzzrank.reporting.json_report import atomic_write_chunks, serializable

STYLE = """
:root{color-scheme:light dark;font:15px system-ui,sans-serif;line-height:1.5}
body{max-width:1200px;margin:2rem auto;padding:0 1.4rem;background:#f4f6f8;color:#14222f}
body{overflow-wrap:anywhere}
h1{margin-bottom:0;color:#123a52}h2{margin-top:2rem}small{color:#46596b}
.stats{display:flex;flex-wrap:wrap;gap:1rem;margin:1.4rem 0}.stat{background:white;
padding:1rem 1.5rem;border:1px solid #d7e1e8;border-radius:6px}
.stat strong{display:block;font-size:1.6rem}
.candidate{background:white;border:1px solid #d7e1e8;border-left:4px solid #27788b;
border-radius:6px;padding:.9rem 1rem;margin:.7rem 0;overflow-wrap:anywhere}
.score{display:inline-block;min-width:3rem;font-weight:750;color:#07576c}
summary{cursor:pointer}code,pre{font-family:ui-monospace,monospace}pre{white-space:pre-wrap;
overflow-wrap:anywhere;font-size:.8rem;max-height:25rem;overflow:auto}
.meta{color:#425969;margin:.4rem 0}.warning{background:#fff0ce;padding:.7rem}
input,select{font:inherit;padding:.6rem;margin:.5rem .5rem .5rem 0;max-width:100%;
box-sizing:border-box}
input{width:30rem}li{margin:.2rem 0}table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:.4rem;border-bottom:1px solid #bacbd8}a{color:#07576c}
nav{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}.filters{display:flex;flex-wrap:wrap;
gap:.5rem;align-items:end}.filters label{display:flex;flex-direction:column;
min-width:0;max-width:100%}
input[type=checkbox]{width:auto}.filters .toggle{display:block;padding:.8rem}
button{font:inherit;padding:.6rem;cursor:pointer}.table-scroll{overflow:auto}
.cluster{padding:1rem;margin:.5rem 0;border:1px solid #bacbd8;border-radius:6px}
[hidden]{display:none!important}.bands{display:flex;gap:1.4rem;flex-wrap:wrap}
@media(prefers-color-scheme:dark){body{background:#121a22;color:#e1e9ef}
h1,.score,a{color:#80d8ed}.candidate,.stat{background:#1c2a35;border-color:#374c5c}
.meta,small{color:#c1d1dc}.warning{background:#443b20}}
@media print{input,select{display:none}body{background:white;color:black}
.candidate{break-inside:avoid}}
"""
SCRIPT = """
const ids = ['search', 'category', 'status', 'engine', 'media', 'cluster-filter', 'noise'];
const controls = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
const entries = Array.from(document.querySelectorAll('.candidate'), card => ({
  card, text: card.textContent.toLowerCase(),
  statuses: JSON.parse(card.dataset.statuses), engines: JSON.parse(card.dataset.engines),
  types: JSON.parse(card.dataset.types)
}));
function filter() {
  const needle = controls.search.value.toLowerCase().trim();
  let count = 0;
  entries.forEach(({card, text, statuses, engines, types}) => {
    const match = text.includes(needle) &&
      (!controls.category.value || card.dataset.category === controls.category.value) &&
      (!controls.status.value || statuses.includes(controls.status.value)) &&
      (!controls.engine.value || engines.includes(controls.engine.value)) &&
      (!controls.media.value || types.includes(controls.media.value)) &&
      (!controls['cluster-filter'].value ||
        card.dataset.cluster === controls['cluster-filter'].value) &&
      (controls.noise.checked || card.dataset.suppressed === 'false');
    card.hidden = !match;
    if (match) count++;
  });
  document.getElementById('noise-section').hidden = !controls.noise.checked;
  document.getElementById('noise-details').open = controls.noise.checked;
  document.getElementById('matches').textContent = count + ' matching endpoint records';
}
function reset() {
  ids.forEach(id => { controls[id].value = ''; });
  controls.noise.checked = false;
}
ids.forEach(id => controls[id].addEventListener(id === 'search' ? 'input' : 'change', filter));
document.getElementById('reset').addEventListener('click', () => { reset(); filter(); });
document.querySelectorAll('[data-select-cluster]').forEach(button => {
  button.addEventListener('click', () => {
    reset(); controls['cluster-filter'].value = button.dataset.selectCluster;
    controls.noise.checked = true; filter();
    document.getElementById('queue').scrollIntoView();
  });
});
document.querySelectorAll('[data-candidate]').forEach(link => {
  link.addEventListener('click', () => {
    reset(); controls.noise.checked = true; filter();
    document.getElementById(link.dataset.candidate).querySelector('details').open = true;
  });
});
filter();
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def card(candidate: Candidate) -> str:
    reasons = "".join(
        f"<li><strong>{r.points:+}</strong> {esc(r.reason)} <small>({esc(r.rule_id)})</small></li>"
        for r in candidate.score_reasons
    )
    fp = candidate.fingerprint
    fingerprints = (
        f"Raw SHA-256: {fp.raw_sha256}\nNormalized SHA-256: {fp.normalized_sha256}\n"
        f"Normalization: {fp.normalization}\nComplete body: {fp.complete}"
        if fp
        else "Body evidence unavailable"
    )
    provenance = "".join(
        f"<tr><td>{esc(o.engine)}</td><td>{o.status_code}</td>"
        f"<td>{esc(o.content_type or 'Unknown')}</td><td>{esc(o.content_length)}</td>"
        f"<td>{esc(o.source)} · record {o.record}</td><td>{esc(o.timestamp)}</td></tr>"
        for o in candidate.observations
    )
    notes = sorted({note for o in candidate.observations for note in o.evidence_notes})
    gaps = "; ".join(candidate.evidence_gaps) or "Complete body and baseline comparison available"
    statuses = json.dumps(sorted({str(o.status_code) for o in candidate.observations}))
    types = json.dumps(sorted({o.content_type or "Unknown" for o in candidate.observations}))
    return f"""<article class="candidate" id="{esc(candidate.id)}"
    data-category="{esc(candidate.category)}" data-cluster="{esc(candidate.response_cluster)}"
    data-statuses="{esc(statuses)}" data-types="{esc(types)}"
    data-engines="{esc(json.dumps(candidate.engines))}"
    data-suppressed="{str(candidate.suppressed).lower()}">
    <details><summary><span class="score">{candidate.score}</span>
    <strong>{esc(candidate.method)} {esc(candidate.path)}</strong> ·
    {esc(candidate.category)}</summary>
    <div class="meta">Status {candidate.primary.status_code} ·
    {esc(candidate.primary.content_type or "Unknown content type")} ·
    Found by {esc(", ".join(candidate.engines))}</div>
    <p>URL: <code>{esc(candidate.url)}</code><br>
    Title: {esc(fp.title if fp and fp.title else "Unavailable")}<br>
    Location: <code>{esc(candidate.primary.location or "None")}</code><br>
    Cluster: {esc(candidate.response_cluster)} ({candidate.cluster_size} endpoints)<br>
    Baseline: {esc(candidate.baseline)}; similarity: {esc(candidate.baseline_similarity)}<br>
    Evidence support: {esc(candidate.evidence_quality)} · {esc(gaps)}<br>
    Evidence conflict: {candidate.evidence_conflict}<br>
    Suppression: {esc(candidate.suppression_reason or "Retained")}</p>
    <ol>{reasons}</ol><pre>{esc(fingerprints)}</pre>
    <h3>Provenance · {len(candidate.observations)} observations</h3>
    <div class="table-scroll"><table><thead><tr><th>Engine</th><th>Status</th><th>Type</th>
    <th>Bytes</th><th>Source / record</th><th>Captured</th></tr></thead>
    <tbody>{provenance}</tbody></table></div><p>{esc("; ".join(notes))}</p>
    </details></article>"""


def select(identifier: str, label: str, values: list[str]) -> str:
    options = "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)
    return (
        f'<label for="{identifier}">{label}<select id="{identifier}">'
        f'<option value="">All</option>{options}</select></label>'
    )


def chunks(report: Report) -> Iterator[str]:
    digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    style_digest = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    csp = (
        f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'sha256-{style_digest}'; "
        "img-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    )
    stats = "".join(
        f'<div class="stat"><strong>{value}</strong>{esc(key.replace("_", " "))}</div>'
        for key, value in report.summary.items()
        if key in {"raw_discoveries", "noise_suppressed", "unique_candidates"}
    )
    warnings = "".join(f'<p class="warning">{esc(w)}</p>' for w in report.warnings)
    filters = "".join(
        select(identifier, label, values)
        for identifier, label, values in [
            ("category", "Priority", ["INSPECT NOW", "HIGH", "MEDIUM", "LOW"]),
            (
                "status",
                "Status",
                sorted({str(o.status_code) for c in report.candidates for o in c.observations}),
            ),
            ("engine", "Engine", sorted({e for c in report.candidates for e in c.engines})),
            (
                "media",
                "Content type",
                sorted(
                    {o.content_type or "Unknown" for c in report.candidates for o in c.observations}
                ),
            ),
            ("cluster-filter", "Cluster", [c["id"] for c in report.clusters]),
        ]
    )
    bands = "".join(
        f"<span><strong>{report.summary.get(key, 0)}</strong> {label}</span>"
        for key, label in [
            ("inspect_now", "Inspect now"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ]
    )
    yield f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="{esc(csp)}">
    <title>FuzzRank report</title><style>{STYLE}</style></head><body>
    <header><h1>FuzzRank</h1><p>Deterministic endpoint review priorities</p>
    <p><strong>Target:</strong> {esc(report.target)}<br>
    <strong>Scope:</strong> {esc(", ".join(report.scope))}<br>
    <strong>Profile:</strong> {esc(report.profile)} ·
    <strong>Run:</strong> {"PARTIAL" if report.partial else "Complete"}</p></header>
    <p>FuzzRank prioritizes discovered endpoints. It does not claim that a candidate is vulnerable.
    Source archives preserve original evidence. Bodies are never interpreted as HTML.</p>
    <nav aria-label="Report sections"><a href="#queue">Investigation queue</a>
    <a href="#clusters">Clusters</a><a href="#baselines">Baselines</a>
    <a href="#diagnostics">Import diagnostics</a><a href="#export">Export metadata</a></nav>
    <div class="stats">{stats}</div><div class="bands">{bands}</div>
    <h2 id="queue">Prioritized candidates</h2><div class="filters">
    <label for="search">Search endpoint records
    <input id="search" type="search" placeholder="Path, status, reason, engine…">
    </label>{filters}<label class="toggle"><input id="noise" type="checkbox">
    Include suppressed noise</label><button id="reset" type="button">Reset filters</button></div>
    <p id="matches" role="status" aria-live="polite"></p>
    <noscript>Enable JavaScript for filters.
    All evidence details remain readable below.</noscript>"""
    for candidate in report.candidates:
        if not candidate.suppressed:
            yield card(candidate)
    yield (
        f'<section id="noise-section"><h2>Suppressed noise '
        f'({report.summary["noise_suppressed"]})</h2><details id="noise-details">'
        "<summary>Inspect suppressed endpoints</summary>"
    )
    for candidate in report.candidates:
        if candidate.suppressed:
            yield card(candidate)
    yield '</details></section><h2 id="clusters">Response clusters</h2>'
    by_id = {candidate.id: candidate for candidate in report.candidates}
    for cluster in report.clusters:
        representative, cluster_id = esc(cluster["representative"]), esc(cluster["id"])
        selected = by_id[cluster["representative"]]
        lengths = cluster.get("length_range")
        size = f"{lengths[0]}–{lengths[1]} bytes" if lengths else "Size unavailable"
        reason = "; ".join(cluster.get("suppression_reasons", [])) or "No members suppressed"
        yield (
            f'<details class="cluster"><summary><strong>{cluster_id}</strong> · '
            f"{cluster['size']} endpoints · {cluster.get('observation_count', cluster['size'])} "
            f"observations · {esc(cluster['classification'])}</summary>"
            f'<p><a href="#{representative}" data-candidate="{representative}">'
            f"Representative: {esc(selected.method)} {esc(selected.path)}</a> · "
            f'<button data-select-cluster="{cluster_id}">Browse members</button></p>'
            f"<p>Status: {esc(', '.join(map(str, cluster.get('statuses', []))))} · "
            f"{esc(size)}<br>Types: {esc(', '.join(cluster.get('content_types', [])))}<br>"
            f"Found by: {esc(', '.join(cluster.get('engines', [])))}<br>"
            f"Suppressed: {cluster['suppressed']} · {esc(reason)}</p>"
            f"<details><summary>Cluster metadata</summary>"
            f"<pre>{esc(json.dumps(cluster, indent=2))}</pre></details></details>"
        )
    yield (
        f'<h2 id="baselines">Baseline information</h2><p>{len(report.baselines)} observations. '
        "Absent or incomplete evidence reduces comparison support; no baseline is invented.</p>"
    )
    cache = FingerprintCache()
    for item in report.baselines:
        row = {
            f.name: serializable(getattr(item, f.name)) for f in fields(item) if f.name != "body"
        }
        row["fingerprint"] = serializable(cache.get(item))
        yield (
            f"<details><summary>{esc(item.method)} {esc(item.url)}</summary>"
            f"<pre>{esc(json.dumps(row, indent=2))}</pre></details>"
        )
    yield f"""<h2 id="diagnostics">Import diagnostics</h2>{warnings}
    <details><summary>{len(report.import_diagnostics)} detailed diagnostics</summary>
    <pre>{esc(json.dumps(report.import_diagnostics, indent=2))}</pre></details>
    <h2>Scoring configuration</h2><details><summary>Exact rules and profile used</summary>
    <pre>{esc(json.dumps(report.configuration, indent=2))}</pre></details>
    <h2 id="export">Export metadata</h2><details>
    <summary>Schema, provenance and run settings</summary>
    <pre>{
        esc(
            json.dumps(
                {
                    "schema_version": report.schema_version,
                    "schema_revision": report.schema_revision,
                    "metadata": report.metadata,
                    "summary": report.summary,
                    "sources": report.sources,
                },
                indent=2,
            )
        )
    }</pre>
    </details><footer><p>Fully offline · authorized use only · no external resources.</p></footer>
    <script>{SCRIPT}</script></body></html>"""


def render(report: Report) -> str:
    return "".join(chunks(report))


def write(report: Report, path: Path) -> None:
    atomic_write_chunks(path, (chunk.encode("utf-8") for chunk in chunks(report)))
