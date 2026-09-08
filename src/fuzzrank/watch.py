"""Debounced local-file observation; no engine launch or HTTP client."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from fuzzrank.inputs import discover, signature
from fuzzrank.models import Report
from fuzzrank.reporting import html_report, json_report
from fuzzrank.service import Investigation


def file_state(
    paths: list[Path], baselines: list[Path], output: Path, recursive: bool, max_files: int
) -> tuple:
    entries = discover(
        paths + baselines, recursive=recursive, excluded=[output], max_files=max_files
    )
    state = []
    for path in entries:
        try:
            state.append((str(path), signature(path)))
        except OSError:
            state.append((str(path), None))
    return tuple(sorted(state))


def publish(report: Report, root: Path, generation: int, reports: str = "both") -> dict:
    directory = root / "generations" / f"{generation:06d}"
    directory.mkdir(parents=True, exist_ok=False)
    report.metadata.update(generation=generation, evidence_root="../..")
    manifest = {
        "format": "fuzzrank-watch-index",
        "generation": generation,
        "partial": report.partial,
        "summary": report.summary,
        "sources": report.sources,
        "warnings": report.warnings,
        "import_diagnostics": report.import_diagnostics,
        "reports": {},
    }
    if reports in {"both", "json"}:
        json_report.write(report, directory / "report.json")
        manifest["reports"]["json"] = f"generations/{generation:06d}/report.json"
    if reports in {"both", "html"}:
        html_report.write(report, directory / "report.html")
        manifest["reports"]["html"] = f"generations/{generation:06d}/report.html"
    json_report.atomic_write(directory / "snapshot.json", json.dumps(manifest, indent=2).encode())
    # The commit pointer changes only once all requested reports are complete.
    json_report.atomic_write(root / "latest.json", json.dumps(manifest, indent=2).encode())
    if "html" in manifest["reports"]:
        link = manifest["reports"]["html"]
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">'
            "<title>FuzzRank watch</title><h1>FuzzRank watch</h1>"
            f'<p>Completed update {generation}</p><p><a href="{link}">Open latest report</a></p>'
            "<p>Reload this index to see subsequent updates.</p></html>"
        )
        json_report.atomic_write(root / "index.html", page.encode())
    return manifest


def watch(
    investigation: Investigation,
    paths: list[Path],
    baselines: list[Path],
    *,
    recursive: bool = False,
    format_name: str = "auto",
    interval: float = 0.5,
    debounce: float = 0.75,
    max_updates: int | None = None,
    reports: str = "both",
    stop: threading.Event | None = None,
    on_report: Callable | None = None,
    on_error: Callable | None = None,
) -> int:
    if not 0.05 <= interval <= 60 or not 0.05 <= debounce <= 30:
        raise ValueError("Poll interval must be 0.05–60 seconds; debounce must be 0.05–30 seconds")
    if max_updates is not None and max_updates < 1:
        raise ValueError("max_updates must be positive")
    if reports not in {"both", "json", "html", "none"}:
        raise ValueError("Invalid report selection")
    stop = stop or threading.Event()
    observed, committed, changed_at = None, None, time.monotonic()
    generation, last_error, retry_after = 0, None, 0.0
    while not stop.is_set():
        try:
            current = file_state(
                paths,
                baselines,
                investigation.loader.output,
                recursive,
                investigation.loader.limits.files,
            )
            now = time.monotonic()
            if current != observed:
                observed, changed_at = current, now
                retry_after = 0.0
            if current != committed and now - changed_at >= debounce and now >= retry_after:
                report = investigation.refresh(
                    paths, baselines, format_name=format_name, recursive=recursive, watching=True
                )
                generation += 1
                manifest = publish(report, investigation.loader.output, generation, reports)
                committed, last_error = current, None
                if on_report:
                    on_report(report, manifest)
                if max_updates is not None and generation >= max_updates:
                    return generation
        except (OSError, ValueError) as exc:
            message = str(exc)
            if message != last_error and on_error:
                on_error(message)
            last_error = message
            retry_after = time.monotonic() + 5.0
        stop.wait(interval)
    return generation
