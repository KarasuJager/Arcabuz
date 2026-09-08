"""Local synthetic benchmark; reports actual elapsed time and traced Python allocations."""

import argparse
import json
import time
import tracemalloc
from pathlib import Path

from fuzzrank.cli import prepare_output
from fuzzrank.config import load_configuration
from fuzzrank.reporting import html_report, json_report
from fuzzrank.service import Investigation


def run(count: int, output: Path) -> dict:
    output = prepare_output(output)
    source = output / "synthetic.ndjson"
    body = "Synthetic wildcard page with enough text to compare response fingerprints safely."
    with source.open("w", encoding="utf-8") as stream:
        for index in range(count):
            row = {
                "type": "response",
                "url": f"https://fixture.example/path-{index // 2}",
                "status": 200,
                "content_length": len(body),
                "content_type": "text/html",
                "body": body,
                "method": "GET",
            }
            stream.write(json.dumps(row) + "\n")
    # Explicit input lives outside the generated analysis folder; no discovery recursion.
    results = prepare_output(output / "analysis")
    tracemalloc.start()
    start = time.perf_counter()
    report = Investigation(results, *load_configuration()).refresh([source], [])
    analyzed = time.perf_counter()
    json_report.write(report, results / "report.json")
    json_done = time.perf_counter()
    html_report.write(report, results / "report.html")
    done = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    measurement = {
        "observations": count,
        "input_bytes": source.stat().st_size,
        "analysis_seconds": round(analyzed - start, 3),
        "json_seconds": round(json_done - analyzed, 3),
        "html_seconds": round(done - json_done, 3),
        "total_seconds": round(done - start, 3),
        "peak_python_mib": round(peak / 1024**2, 2),
        "json_bytes": (results / "report.json").stat().st_size,
        "html_bytes": (results / "report.html").stat().st_size,
        "summary": report.summary,
        "fingerprints": report.metadata["fingerprint_cache_entries"],
    }
    (output / "measurement.json").write_text(json.dumps(measurement, indent=2))
    return measurement


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=20000, choices=range(2, 100001))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.records, args.output), indent=2))
