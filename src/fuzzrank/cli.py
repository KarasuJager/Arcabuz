from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.text import Text

from fuzzrank import __version__
from fuzzrank.config import load_configuration
from fuzzrank.demo import collect_demo
from fuzzrank.doctor import inspect, seclists_locations
from fuzzrank.engines import ADAPTERS
from fuzzrank.engines.base import MAX_FILE_BYTES, MAX_RECORDS, MAX_TOTAL_INPUT_BYTES, read_input
from fuzzrank.inputs import OUTPUT_MARKER, InputLimits
from fuzzrank.pipeline import analyze
from fuzzrank.reporting import html_report, json_report
from fuzzrank.reporting.console import print_report, safe
from fuzzrank.scope import Scope
from fuzzrank.service import Investigation
from fuzzrank.watch import watch


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fuzzrank",
        description="Deterministic offline triage of authorized web discovery results.",
        epilog="Analyze existing evidence or run the local demo. No arbitrary-target scans.",
    )
    parser.add_argument("--version", action="version", version=f"FuzzRank {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--profile", default="generic", help="generic, web, api, or profile YAML path"
    )
    common.add_argument("--rules", type=Path, help="Validated scoring rules YAML")
    common.add_argument("--output", type=Path, help="New or empty output directory")
    common.add_argument(
        "--reports",
        choices=["both", "json", "html", "none"],
        default="both",
        help="Files to generate; original inputs are always archived",
    )
    common.add_argument("--top", type=int, default=15, help="Number of terminal candidates (1–100)")
    common.add_argument("--verbose", action="store_true", help="Include comparison metadata")
    common.add_argument(
        "--quiet", action="store_true", help="Hide progress and summary; errors remain"
    )
    for name, help_text in [
        ("analyze", "Analyze saved files or a directory without HTTP"),
        ("watch", "Watch local output files; never launch fuzzers"),
    ]:
        command = commands.add_parser(name, parents=[common], help=help_text)
        command.add_argument("inputs", type=Path, nargs="+", help="Local result files/directories")
        command.add_argument("--format", choices=["auto", *ADAPTERS], default="auto")
        command.add_argument(
            "--target", help="Target origin; required for relative Gobuster results"
        )
        command.add_argument("--scope", type=Path, help="Additional exact HTTP(S) origins")
        command.add_argument(
            "--recursive", action="store_true", help="Include nested input folders"
        )
        command.add_argument(
            "--baseline",
            action="append",
            type=Path,
            default=[],
            help="Known nonexistent-path captures in any supported format",
        )
        command.add_argument(
            "--max-file-mb", type=int, help="Input-file MiB limit (default 64, max 256)"
        )
        command.add_argument(
            "--max-total-mb", type=int, help="Combined MiB limit (default 128, max 512)"
        )
        command.add_argument(
            "--max-records", type=int, help="Observation limit (default/max 100000)"
        )
        command.add_argument("--max-files", type=int, default=1000, help="File limit (max 10000)")
        if name == "watch":
            command.add_argument("--poll-interval", type=float, default=0.5)
            command.add_argument(
                "--debounce",
                type=float,
                default=0.75,
                help="Require unchanged file metadata for this many seconds",
            )
            command.add_argument("--max-updates", type=int, help="Stop after N published updates")
    command = commands.add_parser("demo", parents=[common], help="Run a closed local HTTP fixture")
    command.add_argument(
        "--max-requests",
        type=int,
        default=64,
        help="Hard demo cap, including baselines (3–1000; 47 planned)",
    )
    command = commands.add_parser("doctor", help="Inspect runtime and optional engine versions")
    command.add_argument("--json", action="store_true", help="Machine-readable diagnostics")
    command.add_argument("--wordlist", type=Path, help="Inspect a local wordlist without using it")
    commands.add_parser("wordlists", help="Show optional SecLists locations and profile hints")
    return parser


def prepare_output(path: Path | None) -> Path:
    if path is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        path = Path("results") / stamp
    if path.is_symlink():
        raise ValueError("Output directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError(f"Output directory is not empty: {path}; choose a new directory")
    (path / OUTPUT_MARKER).write_text("FuzzRank generated output; exclude from input discovery.\n")
    return path.resolve()


def _limits(args) -> InputLimits:
    return InputLimits(
        file_bytes=MAX_FILE_BYTES if args.max_file_mb is None else args.max_file_mb * 1024**2,
        total_bytes=MAX_TOTAL_INPUT_BYTES
        if args.max_total_mb is None
        else args.max_total_mb * 1024**2,
        records=MAX_RECORDS if args.max_records is None else args.max_records,
        files=args.max_files,
    )


def run(args, console: Console) -> int:
    if args.command == "doctor":
        data = inspect()
        if args.wordlist:
            content = read_input(args.wordlist)
            data["wordlist"] = {
                "path": str(args.wordlist.resolve()),
                "bytes": len(content),
                "entries": sum(
                    bool(line.strip()) and not line.lstrip().startswith(b"#")
                    for line in content.splitlines()
                ),
                "used_for_requests": False,
            }
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            console.print("FuzzRank doctor", style="bold cyan")
            console.print(Text(f"Python {data['python']} - {data['executable']}"))
            for name, item in data["engines"].items():
                detail = "; ".join(
                    str(item[key]) for key in ("version", "warning") if item.get(key)
                )
                console.print(Text(f"{name}: {safe(detail)}"))
            console.print(
                Text("SecLists: " + (", ".join(data["seclists"]) or "not found (optional)"))
            )
            if "wordlist" in data:
                console.print(Text(str(data["wordlist"])))
            console.print("External tools only: FuzzRank never launches arbitrary-target scans.")
            console.print("Missing engines do not prevent offline analysis.")
        return 0 if data["supported_runtime"] else 1
    if args.command == "wordlists":
        console.print(
            Text("SecLists locations: " + (", ".join(seclists_locations()) or "not found"))
        )
        for name in ("generic", "web", "api"):
            profile, _ = load_configuration(name)
            console.print(Text(name + ": " + ", ".join(profile["wordlist_hints"])))
        console.print("Hints only. No wordlist is downloaded or used for requests.")
        return 0
    if not 1 <= args.top <= 100:
        raise ValueError("--top must be between 1 and 100")
    profile, rules = load_configuration(args.profile, args.rules)
    if args.command == "demo" and not 3 <= args.max_requests <= 1000:
        raise ValueError("--max-requests must be between 3 and 1000")
    output = prepare_output(args.output)

    def announce(phase: int, message: str):
        if not args.quiet:
            console.print(Text(f"[{phase}/6] {safe(message)}"))

    requests = 0
    if args.command in {"analyze", "watch"}:
        investigation = Investigation(
            output, profile, rules, target=args.target, scope_file=args.scope, limits=_limits(args)
        )
        if args.command == "watch":
            if not args.quiet:
                console.print("Watching local result files. No fuzzer or request will be launched.")
            last_partial = False

            def updated(report, manifest):
                nonlocal last_partial
                last_partial = report.partial
                if not args.quiet:
                    console.print(f"Update {manifest['generation']}", style="bold cyan")
                    print_report(report, console, args.top, args.verbose)
                    console.print(Text("Latest snapshot: " + str(output / "latest.json")))

            def failed(message):
                Console(stderr=True).print(Text("Watch: " + safe(message), style="yellow"))

            watch(
                investigation,
                args.inputs,
                args.baseline,
                recursive=args.recursive,
                format_name=args.format,
                interval=args.poll_interval,
                debounce=args.debounce,
                max_updates=args.max_updates,
                reports=args.reports,
                on_report=updated,
                on_error=failed,
            )
            return 3 if last_partial else 0
        announce(1, "Validating scope and discovering local inputs")
        announce(2, "Loading explicit or tagged baseline observations")
        announce(3, "Importing saved results without network requests")
        announce(4, "Normalizing evidence and merging repeated observations")
        announce(5, "Clustering and applying explainable scoring rules")
        report = investigation.refresh(
            args.inputs, args.baseline, format_name=args.format, recursive=args.recursive
        )
    else:
        target, observations, baselines, warnings, partial, requests = collect_demo(
            output, args.max_requests, announce
        )
        scope, sources, rejected, ignored = Scope.load(target), [], 0, 0
        announce(4, "Normalizing evidence and merging repeated endpoint observations")
        announce(5, "Clustering responses and applying explainable scoring rules")
        report = analyze(observations, baselines, scope, profile, rules, warnings)
        report.sources, report.partial = sources, partial
        report.summary.update(
            rejected_records=rejected, ignored_events=ignored, requests_made=requests
        )
    announce(6, "Generating JSON and standalone HTML reports")
    if args.reports in {"both", "json"}:
        json_report.write(report, output / "report.json")
    if args.reports in {"both", "html"}:
        html_report.write(report, output / "report.html")
    if not args.quiet:
        print_report(report, console, args.top, args.verbose)
        console.print(Text("Reports: " + str(output)))
    return 3 if report.partial else 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    console = Console(highlight=False)
    try:
        return run(args, console)
    except KeyboardInterrupt:
        Console(stderr=True).print(
            "Interrupted. Completed source archives, report snapshots and demo checkpoints remain."
        )
        return 130
    except (OSError, ValueError, UnicodeError) as exc:
        Console(stderr=True).print(Text("FuzzRank error: " + safe(exc), style="red"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
