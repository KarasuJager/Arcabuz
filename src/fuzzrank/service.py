"""Shared analysis service for CLI, watch, and future UI clients."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fuzzrank.inputs import InputLimits, InputLoader
from fuzzrank.models import Report
from fuzzrank.pipeline import analyze
from fuzzrank.scope import Scope, origin


class Investigation:
    def __init__(
        self,
        output: Path,
        profile: dict,
        rules: dict,
        *,
        target: str | None = None,
        scope_file: Path | None = None,
        limits: InputLimits | None = None,
    ):
        self.loader = InputLoader(output, limits)
        self.profile, self.rules = profile, rules
        self.target, self.scope_file = target, scope_file
        # Validate explicit scope before processing any source evidence.
        self.scope = Scope.load(target, scope_file) if target else None

    def refresh(
        self,
        paths: list[Path],
        baselines: list[Path],
        *,
        format_name: str = "auto",
        recursive: bool = False,
        watching: bool = False,
    ) -> Report:
        loaded = self.loader.load(
            paths,
            baselines,
            target=self.target,
            format_name=format_name,
            recursive=recursive,
            retain_last_good=watching,
        )
        if self.scope is None:
            if not loaded.observations:
                raise ValueError("No valid discovery records. " + "; ".join(loaded.warnings[:3]))
            self.target = origin(loaded.observations[0].url)
            self.scope = Scope.load(self.target, self.scope_file)
        if not loaded.observations and not watching:
            raise ValueError("No valid discovery records. " + "; ".join(loaded.warnings[:3]))
        report = analyze(
            loaded.observations,
            loaded.baselines,
            self.scope,
            self.profile,
            self.rules,
            loaded.warnings,
        )
        report.sources, report.partial = loaded.sources, loaded.partial
        report.import_diagnostics = loaded.diagnostics
        report.summary.update(
            rejected_records=loaded.rejected_records,
            ignored_events=loaded.ignored_records,
            requests_made=0,
        )
        report.metadata.update(input_limits=asdict(self.loader.limits), evidence_root=".")
        return report
