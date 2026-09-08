"""View data only: no independent analysis or scoring decisions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from fuzzrank.analysis.fingerprint import FingerprintCache
from fuzzrank.models import Candidate, Report


def plain(value: object) -> str:
    """Keep native widgets literal, with visible controls rather than terminal/bidi escapes."""
    return "".join(
        c
        if c >= " " and c not in "\x7f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
        else " "
        for c in str(value)
    )


def tooltip(value: object) -> str:
    """Qt auto-detects rich tooltips: escape evidence before using fixed markup."""
    text = plain(value)
    if len(text) > 8192:
        text = text[:8192] + "… (View full row or copy the cell for the complete value)"
    return "<qt>" + escape(text) + "</qt>"


def compact(value: object, kind: str = "") -> str:
    text = "Unknown" if value == -1 else plain(value)
    if kind == "id" and len(text) > 16:
        return text[:8] + "…" + text[-4:]
    if kind == "hash" and len(text) > 20:
        return text[:8] + "…" + text[-6:]
    if kind == "media":
        return text.split(";", 1)[0]
    if kind == "filename":
        return text.replace("\\", "/").rsplit("/", 1)[-1]
    if kind == "time" and len(text) >= 19 and text[10:11] == "T":
        return text[:19].replace("T", " ")
    return text


@dataclass(frozen=True)
class CandidateRow:
    candidate: Candidate
    values: tuple
    search: str
    statuses: frozenset[str]
    engines: frozenset[str]
    types: frozenset[str]


@dataclass
class ViewData:
    report: Report
    directory: Path
    candidates: list[CandidateRow]
    clusters: list[tuple]
    baselines: list[tuple]
    sources: list[tuple]
    changed: tuple[str, ...] = ()


def present(report: Report, directory: Path, changed=()) -> ViewData:
    rows = []
    for candidate in report.candidates:
        item = candidate.primary
        values = (
            candidate.score,
            candidate.category,
            candidate.method,
            item.status_code,
            candidate.path,
            urlsplit(candidate.url).netloc,
            item.content_type or "Unknown",
            item.content_length if item.content_length is not None else -1,
            candidate.response_cluster,
            ", ".join(candidate.engines),
            "Suppressed" if candidate.suppressed else "Retained",
        )
        search = (
            " ".join(map(str, values))
            + " "
            + candidate.url
            + " "
            + " ".join(reason.reason for reason in candidate.score_reasons)
        )
        rows.append(
            CandidateRow(
                candidate,
                values,
                search.casefold(),
                frozenset(str(o.status_code) for o in candidate.observations),
                frozenset(candidate.engines),
                frozenset(o.content_type or "Unknown" for o in candidate.observations),
            )
        )
    by_id = {c.id: c for c in report.candidates}
    clusters = []
    for group in report.clusters:
        representative = by_id[group["representative"]]
        statuses = Counter(
            o.status_code for cid in group["members"] for o in by_id[cid].observations
        )
        sizes = group.get("length_range")
        clusters.append(
            (
                group["id"],
                group.get("observation_count", group["size"]),
                group["size"],
                representative.path,
                ", ".join(f"{s}: {n}" for s, n in sorted(statuses.items())),
                ", ".join(group.get("content_types", [])),
                f"{sizes[0]}–{sizes[1]}" if sizes else "Unknown",
                ", ".join(group.get("engines", [])),
                group["classification"],
                "; ".join(group.get("suppression_reasons", [])) or "No suppression",
            )
        )
    cache, baselines = FingerprintCache(), []
    for item in report.baselines:
        fp = cache.get(item)
        baselines.append(
            (
                item.method,
                item.status_code,
                item.url,
                item.content_type or "Unknown",
                item.content_length if item.content_length is not None else -1,
                fp.raw_sha256 if fp else "Body unavailable",
                fp.normalized_sha256 if fp else "Body unavailable",
                item.location,
                "Incomplete" if item.truncated else "Complete" if fp else "Unavailable",
                item.source,
            )
        )
    all_observations = [o for c in report.candidates for o in c.observations]
    all_observations.extend(report.baselines)
    all_observations.extend(report.excluded)
    counts = Counter(o.source for o in all_observations)
    engines: dict[str, set[str]] = {}
    for item in all_observations:
        engines.setdefault(item.source, set()).add(item.engine)
    diagnostics = Counter(
        d["source"] for d in report.import_diagnostics if d["severity"] == "error"
    )
    sources = [
        (
            s.get("original_path", s["id"]),
            s.get("format", "Unknown"),
            s["status"],
            counts[s["id"]],
            ", ".join(sorted(engines.get(s["id"], []))),
            diagnostics[s["id"]] + diagnostics[s.get("original_path", "")],
            s["id"],
            s["sha256"],
        )
        for s in report.sources
    ]
    if not sources and all_observations:
        sources = [
            (
                name,
                "local evidence",
                "captured",
                count,
                ", ".join(sorted(engines[name])),
                diagnostics[name],
                name,
                "See checkpointed evidence",
            )
            for name, count in sorted(counts.items())
        ]
    clusters.sort(key=lambda row: (-row[2], row[0]))
    return ViewData(report, directory, rows, clusters, baselines, sources, tuple(changed))
