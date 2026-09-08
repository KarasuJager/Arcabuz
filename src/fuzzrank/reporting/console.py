from __future__ import annotations

import re

from rich.console import Console
from rich.table import Table
from rich.text import Text

from fuzzrank.models import Report


def safe(value: object) -> str:
    # Treat remote response metadata as data, including terminal escape sequences.
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "?", str(value))


def print_report(report: Report, console: Console, top: int = 15, verbose: bool = False) -> None:
    console.print("FUZZRANK SUMMARY", style="bold cyan")
    console.print(Text(f"Target: {safe(report.target)}"))
    console.print("Scores express manual investigation priority.")
    if report.partial:
        console.print("PARTIAL RESULTS", style="bold yellow")
    table = Table(show_header=False, box=None, padding=(0, 2))
    for label, key in [
        ("Raw discoveries", "raw_discoveries"),
        ("Out of scope", "out_of_scope"),
        ("Cross-source observations merged", "duplicates_merged"),
        ("Noise suppressed", "noise_suppressed"),
        ("Unique candidates", "unique_candidates"),
        ("Inspect immediately", "inspect_now"),
        ("High interest", "high"),
        ("Medium interest", "medium"),
        ("Low interest", "low"),
    ]:
        table.add_row(label, str(report.summary[key]))
    console.print(table)
    console.print("\nTOP CANDIDATES", style="bold cyan")
    kept = [c for c in report.candidates if not c.suppressed][:top]
    for candidate in kept:
        console.print(
            Text(f"[{candidate.score:02}] {candidate.method} {safe(candidate.path)}", style="bold")
        )
        console.print(
            Text(
                f"     Status: {candidate.primary.status_code}  Type: "
                f"{safe(candidate.primary.content_type) or 'unknown'}"
            )
        )
        console.print(Text("     Found by: " + safe(", ".join(candidate.engines))))
        for reason in candidate.score_reasons:
            console.print(Text(f"       {reason.points:+} {safe(reason.reason)}"))
        if verbose:
            console.print(
                Text(f"     Cluster: {candidate.response_cluster}; baseline: {candidate.baseline}")
            )
            console.print(Text("     Evidence: " + safe(candidate.evidence_quality)))
            for gap in candidate.evidence_gaps:
                console.print(Text("       " + safe(gap)))
    for warning in report.warnings[:30]:
        console.print(Text("Warning: " + safe(warning), style="yellow"))
    if len(report.warnings) > 30:
        console.print("Further warnings are in the JSON and HTML reports.")
