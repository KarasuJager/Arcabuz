"""Local file discovery and evidence loading, independent of terminal rendering."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from fuzzrank.engines import detect, parse
from fuzzrank.engines.base import (
    MAX_FILE_BYTES,
    MAX_RECORDS,
    MAX_TOTAL_INPUT_BYTES,
    BodyPool,
    decode_json,
    read_input,
)
from fuzzrank.models import ImportResult, Observation
from fuzzrank.reporting.json_report import atomic_write

SUFFIXES = {".json", ".jsonl", ".ndjson", ".ejson", ".har", ".txt", ".log"}
OUTPUT_MARKER = ".fuzzrank-output"


@dataclass(frozen=True)
class InputLimits:
    file_bytes: int = MAX_FILE_BYTES
    total_bytes: int = MAX_TOTAL_INPUT_BYTES
    records: int = MAX_RECORDS
    files: int = 1000

    def __post_init__(self):
        for value, maximum in [
            (self.file_bytes, 256 * 1024**2),
            (self.total_bytes, 512 * 1024**2),
            (self.records, MAX_RECORDS),
            (self.files, 10000),
        ]:
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"Input limit must be an integer between 1 and {maximum}")


def _excluded(path: Path, excluded: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in excluded)


def _walk_error(error: OSError) -> None:
    raise error


def discover(
    paths: list[Path],
    *,
    recursive: bool = False,
    excluded: list[Path] | None = None,
    max_files: int = 1000,
) -> list[Path]:
    """Explicit files plus sorted supported directory members. Never follow symlinks."""
    roots = [p.resolve() for p in excluded or []]
    found: dict[Path, None] = {}
    for entry in paths:
        if entry.is_symlink():
            raise ValueError(f"Symlink input is not supported: {entry.name}")
        if not entry.is_dir():
            if not _excluded(entry, roots):
                found[entry.resolve()] = None
            continue
        for directory, dirs, files in os.walk(entry, followlinks=False, onerror=_walk_error):
            folder = Path(directory)
            if _excluded(folder, roots) or (folder / OUTPUT_MARKER).exists():
                dirs[:] = []
                continue
            dirs[:] = (
                sorted(d for d in dirs if not d.startswith(".") and not (folder / d).is_symlink())
                if recursive
                else []
            )
            for name in sorted(files):
                path = folder / name
                if name.startswith(".") or path.suffix.lower() not in SUFFIXES:
                    continue
                if path.is_symlink():
                    raise ValueError(f"Symlink input is not supported: {path.name}")
                if not _excluded(path, roots):
                    found[path.resolve()] = None
                if len(found) > max_files:
                    raise ValueError(
                        f"More than {max_files} input files; select a smaller directory"
                    )
    if len(found) > max_files:
        raise ValueError(f"More than {max_files} input files")
    return list(found)


def signature(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def generated_document(data: bytes) -> bool:
    # Ordinary engine outputs often use the filename report.json too; identify by content.
    if not any(key in data[:8192] for key in (b'"schema_version"', b'"fuzzrank-report"')):
        return False
    try:
        doc = decode_json(data)
    except ValueError:
        return False
    return isinstance(doc, dict) and "schema_version" in doc and "candidates" in doc


@dataclass
class SourceSnapshot:
    signature: tuple
    result: ImportResult
    manifest: dict
    baseline: bool


@dataclass
class LoadedInputs:
    observations: list[Observation] = field(default_factory=list)
    baselines: list[Observation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    partial: bool = False
    rejected_records: int = 0
    ignored_records: int = 0


class InputLoader:
    """Reusable local investigation loader. Cache retains only each file's last usable parse."""

    def __init__(self, output: Path, limits: InputLimits | None = None):
        self.output = output
        self.limits = limits or InputLimits()
        self.cache: dict[Path, SourceSnapshot] = {}

    def _archive(self, path: Path, data: bytes, baseline: bool) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        suffix = path.suffix.lower() if path.suffix.lower() in SUFFIXES else ".bin"
        relative = f"evidence/{digest}{suffix}"
        destination = self.output / relative
        destination.parent.mkdir(exist_ok=True, parents=True)
        if not destination.exists():
            atomic_write(destination, data)
        identity = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        manifest = {
            "id": f"S-{identity}-{digest[:16]}",
            "original_path": path.name,
            "archive": relative,
            "sha256": digest,
            "bytes": len(data),
            "role": "baseline" if baseline else "discovery",
            "status": "accepted",
        }
        # A sidecar makes every completed archive attributable even if parsing is interrupted.
        atomic_write(
            self.output / "evidence" / f"{manifest['id']}.source.json",
            json.dumps(manifest, indent=2).encode(),
        )
        return manifest

    def load(
        self,
        paths: list[Path],
        baseline_paths: list[Path],
        *,
        target: str | None = None,
        format_name: str = "auto",
        recursive: bool = False,
        retain_last_good: bool = False,
    ) -> LoadedInputs:
        loaded, pool = LoadedInputs(), BodyPool()
        files = discover(
            paths, recursive=recursive, excluded=[self.output], max_files=self.limits.files
        )
        explicit_baselines = discover(
            baseline_paths, recursive=recursive, excluded=[self.output], max_files=self.limits.files
        )
        selections = dict.fromkeys(files, False)
        selections.update(dict.fromkeys(explicit_baselines, True))
        if len(selections) > self.limits.files:
            raise ValueError(f"More than {self.limits.files} input files including baselines")
        input_bytes = 0
        for path in list(self.cache):
            if path not in selections:
                previous = self.cache.pop(path)
                loaded.sources.append({**previous.manifest, "status": "removed"})
        for path, baseline in selections.items():
            previous = self.cache.get(path)
            manifest, chosen, failure = None, None, None
            try:
                before = signature(path)
                if (
                    retain_last_good
                    and previous
                    and before == previous.signature
                    and baseline == previous.baseline
                ):
                    chosen = previous
                    manifest = dict(previous.manifest)
                else:
                    if path.is_symlink() or not path.is_file():
                        raise ValueError("Input must be a regular local file")
                    data = read_input(path, self.limits.file_bytes)
                    manifest = self._archive(path, data, baseline)
                    if before != signature(path):
                        raise ValueError(
                            "Input changed while being read; "
                            "archived bytes are not a stable snapshot"
                        )
                    if generated_document(data):
                        loaded.diagnostics.append(
                            {
                                "severity": "info",
                                "source": manifest["id"],
                                "message": "Generated report skipped; import original evidence",
                            }
                        )
                        loaded.sources.append({**manifest, "status": "ignored-report"})
                        continue
                    if input_bytes + len(data) > self.limits.total_bytes:
                        raise ValueError(
                            "Combined input byte limit exceeded; source archived but not parsed"
                        )
                    selected_format = (
                        detect(data) if format_name == "auto" or baseline else format_name
                    )
                    manifest["format"] = selected_format
                    result = parse(data, manifest["id"], selected_format, target)
                    loaded.diagnostics.extend(result.diagnostics)
                    if result.rejected_records:
                        loaded.rejected_records += result.rejected_records
                        loaded.warnings.extend(result.warnings)
                        loaded.partial = True
                        manifest["status"] = "partial"
                    if retain_last_good and previous and result.rejected_records:
                        raise ValueError(
                            "Updated input has malformed records; "
                            "retaining last usable observations"
                        )
                    chosen = SourceSnapshot(before, result, dict(manifest), baseline)
                    if not result.rejected_records:
                        self.cache[path] = chosen
            except (OSError, ValueError, UnicodeError) as exc:
                failure = str(exc).replace(str(path), path.name)
                loaded.partial = True
                loaded.warnings.append(f"{path.name}: {failure}")
                loaded.diagnostics.append(
                    {"severity": "error", "source": path.name, "message": failure}
                )
                if manifest:
                    loaded.sources.append({**manifest, "status": "rejected"})
                if retain_last_good and previous and "limit exceeded" not in failure:
                    chosen = previous
                    manifest = {**previous.manifest, "status": "stale"}
                    loaded.warnings.append(f"{path.name}: using its archived last usable snapshot")
                else:
                    continue
            if chosen is None:
                continue
            size = chosen.manifest["bytes"]
            if input_bytes + size > self.limits.total_bytes:
                loaded.partial = True
                loaded.warnings.append(f"{path.name}: Combined input byte limit exceeded")
                loaded.sources.append({**chosen.manifest, "status": "limit-excluded"})
                continue
            count = (
                len(loaded.observations) + len(loaded.baselines) + len(chosen.result.observations)
            )
            if count > self.limits.records:
                loaded.partial = True
                loaded.warnings.append(
                    f"{path.name}: total observation limit exceeded; source archived"
                )
                loaded.sources.append({**chosen.manifest, "status": "limit-excluded"})
                continue
            input_bytes += size
            loaded.sources.append(manifest or dict(chosen.manifest))
            if retain_last_good and previous is chosen:
                loaded.diagnostics.extend(chosen.result.diagnostics)
            loaded.ignored_records += chosen.result.ignored_records
            chosen.result.observations = [pool.intern(item) for item in chosen.result.observations]
            for item in chosen.result.observations:
                (loaded.baselines if baseline or item.baseline else loaded.observations).append(
                    item
                )
        atomic_write(self.output / "sources.json", json.dumps(loaded.sources, indent=2).encode())
        return loaded
