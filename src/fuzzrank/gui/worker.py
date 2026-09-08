"""Qt worker boundary; uses the same investigation, demo and report services as the CLI."""

from __future__ import annotations

import os
import threading
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from fuzzrank.config import load_configuration
from fuzzrank.demo import collect_demo
from fuzzrank.engines import detect
from fuzzrank.engines.base import read_input
from fuzzrank.gui.presentation import present
from fuzzrank.inputs import InputLimits, discover, prepare_output
from fuzzrank.pipeline import analyze
from fuzzrank.reporting import html_report, json_report, load_report
from fuzzrank.scope import Scope
from fuzzrank.service import Investigation
from fuzzrank.watch import watch


@dataclass
class AnalysisRequest:
    paths: list[Path] = field(default_factory=list)
    baselines: list[Path] = field(default_factory=list)
    profile: str = "generic"
    target: str | None = None
    scope_file: Path | None = None
    output: Path | None = None
    recursive: bool = False
    limits: InputLimits = field(default_factory=InputLimits)
    debounce: float = 0.75
    interval: float = 0.5


class Cancelled(Exception):
    pass


class Worker(QThread):
    ready = Signal(object)
    progress = Signal(str)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, operation: str, payload, parent=None):
        super().__init__(parent)
        self.operation, self.payload = operation, payload
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def checkpoint(self):
        if self.stop_event.is_set():
            raise Cancelled

    def run(self):
        try:
            self.checkpoint()
            result = self.execute()
            self.checkpoint()
            if result is not None:
                self.ready.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            # A worker exception must never disappear or kill the UI event loop.
            self.failed.emit(str(exc)[:1000] or type(exc).__name__, traceback.format_exc())

    def execute(self):
        if self.operation == "preview":
            request = self.payload
            rows, total = [], 0
            for path in discover(
                request.paths, recursive=request.recursive, max_files=request.limits.files
            ):
                self.checkpoint()
                try:
                    data = read_input(path, request.limits.file_bytes)
                    total += len(data)
                    if total > request.limits.total_bytes:
                        raise ValueError("Combined preview byte limit exceeded")
                    rows.append((path.name, detect(data), len(data), "Ready to import"))
                except (OSError, ValueError) as exc:
                    rows.append((path.name, "Unknown", 0, str(exc)[:300]))
            return rows
        if self.operation == "open":
            path = self.payload
            self.progress.emit("Validating saved report and restoring evidence")
            report = load_report.read(path)
            self.checkpoint()
            return present(report, path.parent)
        if self.operation == "export":
            report, source_dir, destination, kind = self.payload
            root = report.metadata.get("evidence_root", ".")
            # References remain data. Never read/copy paths named by imported report metadata.
            root = root if isinstance(root, str) else "."
            evidence_root = os.path.abspath(os.path.join(source_dir, root))
            try:
                reference = os.path.relpath(evidence_root, destination.parent)
            except ValueError:  # Different Windows drives cannot have a relative path.
                reference = evidence_root
            exported = replace(report, metadata={**report.metadata, "evidence_root": reference})
            self.progress.emit(f"Exporting {kind.upper()} report")
            (json_report if kind == "json" else html_report).write(exported, destination)
            return destination
        request = self.payload
        profile, rules = load_configuration(request.profile)
        if request.target:
            Scope.load(request.target, request.scope_file)
        self.checkpoint()
        output = prepare_output(request.output)
        if self.operation == "demo":
            self.progress.emit("Running the built-in loopback demonstration")
            target, observations, baselines, warnings, partial, count = collect_demo(
                output, announce=lambda _, message: self.progress.emit(message)
            )
            self.checkpoint()
            report = analyze(observations, baselines, Scope.load(target), profile, rules, warnings)
            report.partial = partial
            report.summary.update(requests_made=count, rejected_records=0, ignored_events=0)
        else:
            investigation = Investigation(
                output,
                profile,
                rules,
                target=request.target,
                scope_file=request.scope_file,
                limits=request.limits,
            )
            if self.operation == "watch":
                previous = {}

                def updated(report, _):
                    nonlocal previous
                    self.checkpoint()
                    current = {
                        s["id"].rsplit("-", 1)[0]: (
                            s["sha256"],
                            s["status"],
                            s.get("original_path", s["id"]),
                        )
                        for s in report.sources
                    }
                    changed = sorted(
                        (current.get(name) or previous[name])[2]
                        for name in current.keys() | previous.keys()
                        if current.get(name) != previous.get(name)
                    )
                    previous = current
                    self.ready.emit(
                        present(
                            report,
                            output / "generations" / f"{report.metadata['generation']:06d}",
                            changed,
                        )
                    )

                self.progress.emit("Watching local evidence for stable changes")
                watch(
                    investigation,
                    request.paths,
                    request.baselines,
                    recursive=request.recursive,
                    interval=request.interval,
                    debounce=request.debounce,
                    stop=self.stop_event,
                    on_report=updated,
                    on_error=lambda message: self.progress.emit("Waiting: " + message),
                )
                return None
            self.progress.emit("Importing, normalizing, clustering and scoring with the V1 core")
            report = investigation.refresh(
                request.paths, request.baselines, recursive=request.recursive
            )
        self.checkpoint()
        self.progress.emit("Writing evidence reports")
        json_report.write(report, output / "report.json")
        self.checkpoint()
        html_report.write(report, output / "report.html")
        self.checkpoint()
        return present(report, output)
