#!/usr/bin/env python3
"""Arcabuz — Merge + deduplicate results from multiple fuzzing tools."""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


def extract_ffuf(path: Path) -> list[dict]:
    """Extract results from ffuf JSON output."""
    results = []
    try:
        data = json.loads(path.read_text())
        for r in data.get("results", []):
            results.append({
                "url": r.get("url", ""),
                "status": r.get("status", 0),
                "length": r.get("length", 0),
                "words": r.get("words", 0),
                "lines": r.get("lines", 0),
                "source": "ffuf",
            })
    except Exception:
        pass
    return results


def extract_gobuster(path: Path) -> list[dict]:
    """Extract results from gobuster text output."""
    results = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # gobuster dir format: /path (Status: 200) [Size: 1234]
            if "(Status:" in line:
                parts = line.split("(Status:")
                url = parts[0].strip()
                status = int(parts[1].split(")")[0].strip())
                size = 0
                if "[Size:" in line:
                    size = int(line.split("[Size:")[1].split("]")[0].strip())
                results.append({"url": url, "status": status, "length": size, "source": "gobuster"})
            # gobuster dns format: Found: sub.domain.com
            elif line.startswith("Found:"):
                host = line.replace("Found:", "").strip()
                results.append({"url": host, "status": 0, "source": "gobuster"})
            else:
                results.append({"url": line.split()[0], "status": 0, "source": "gobuster"})
    except Exception:
        pass
    return results


def extract_dirsearch(path: Path) -> list[dict]:
    """Extract results from dirsearch JSON output."""
    results = []
    try:
        data = json.loads(path.read_text())
        for url_key, entries in data.get("results", {}).items():
            for r in entries:
                results.append({
                    "url": r.get("url", ""),
                    "status": r.get("status", 0),
                    "length": r.get("content-length", 0),
                    "source": "dirsearch",
                })
    except Exception:
        pass
    return results


def extract_feroxbuster(path: Path) -> list[dict]:
    """Extract results from feroxbuster text output."""
    results = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or not line.startswith("http"):
                continue
            parts = line.split()
            url = parts[0]
            status = 0
            for p in parts:
                if p.isdigit() and 100 <= int(p) <= 599:
                    status = int(p)
                    break
            results.append({"url": url, "status": status, "source": "feroxbuster"})
    except Exception:
        pass
    return results


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    url = url.rstrip("/").lower()
    return url


def merge_and_dedup(output_dir: Path, mode: str):
    """Merge results from all tools and deduplicate."""
    raw_dir = output_dir / "raw"
    merged_dir = output_dir / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    # Load from each tool
    for f in raw_dir.glob("ffuf*.json"):
        all_results.extend(extract_ffuf(f))
    for f in raw_dir.glob("gobuster*.txt"):
        all_results.extend(extract_gobuster(f))
    for f in raw_dir.glob("dirsearch*.json"):
        all_results.extend(extract_dirsearch(f))
    for f in raw_dir.glob("feroxbuster*.txt"):
        all_results.extend(extract_feroxbuster(f))

    print(f"  Total raw results: {len(all_results)}")

    # Deduplicate by normalized URL
    seen = {}
    duplicates = []

    for r in all_results:
        key = normalize_url(r["url"])
        if key in seen:
            seen[key]["confirmed_by"].append(r["source"])
            duplicates.append(f"{r['url']} (dup from {r['source']}, first seen by {seen[key]['source']})")
        else:
            seen[key] = {**r, "confirmed_by": [r["source"]]}

    unique = sorted(seen.values(), key=lambda x: (-len(x["confirmed_by"]), -x.get("status", 0)))

    # Write unique results
    lines = []
    for r in unique:
        confirmed = ", ".join(sorted(set(r["confirmed_by"])))
        count = len(set(r["confirmed_by"]))
        tag = f"[{count}x: {confirmed}]" if count > 1 else f"[{r['source']}]"
        status = f" ({r['status']})" if r.get("status") else ""
        lines.append(f"{r['url']}{status} {tag}")

    (merged_dir / "unique-results.txt").write_text("\n".join(lines))
    (merged_dir / "duplicates.txt").write_text("\n".join(duplicates))

    # Also save as JSON for FuzzRank triage
    (merged_dir / "results.json").write_text(json.dumps(unique, indent=2))

    print(f"  Unique results: {len(unique)}")
    print(f"  Duplicates removed: {len(duplicates)}")
    print(f"  Multi-tool confirmed: {sum(1 for r in unique if len(set(r['confirmed_by'])) > 1)}")


if __name__ == "__main__":
    output_dir = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "unknown"
    merge_and_dedup(output_dir, mode)
