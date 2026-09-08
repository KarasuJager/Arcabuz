"""Bounded version checks only. Engine scans are never launched."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def version_details(name: str, output: str) -> dict:
    match = re.fullmatch(
        rf"(?:{re.escape(name)}(?:\s+version)?[:\s]+)?v?(\d+)\.(\d+)(?:\.(\d+))?"
        r"(?:[-+][\w.\-]+)?",
        output.strip(),
        re.IGNORECASE,
    )
    if not match or any(ord(char) < 32 for char in output.strip()):
        return {
            "version_check_ok": False,
            "version": "",
            "output": output,
            "warning": "Unrecognized version output; format compatibility is not established",
        }
    supported = int(match[1]) == {"ffuf": 2, "feroxbuster": 2, "gobuster": 3}[name]
    details = {"version_check_ok": True, "version": output, "recognized_version_family": supported}
    if not supported:
        details["warning"] = (
            "Version family not covered by the import fixtures; verify saved format"
        )
    return details


def seclists_locations() -> list[str]:
    candidates = [
        Path("/usr/share/seclists"),
        Path("/usr/share/SecLists"),
        Path("/opt/SecLists"),
        Path.home() / "SecLists",
    ]
    if os.environ.get("SECLISTS_PATH"):
        candidates.insert(0, Path(os.environ["SECLISTS_PATH"]))
    return sorted({str(p.resolve()) for p in candidates if p.is_dir()})


def inspect() -> dict:
    result = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "supported_runtime": sys.version_info >= (3, 11),
        "engines": {},
        "seclists": seclists_locations(),
    }
    for name, flag in [("ffuf", "-V"), ("feroxbuster", "--version"), ("gobuster", "version")]:
        executable = shutil.which(name)
        if not executable:
            result["engines"][name] = {"installed": False, "warning": "Optional executable missing"}
            continue
        process = None
        try:
            process = subprocess.Popen(
                [executable, flag],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output, _ = process.communicate(timeout=3)
            version = output.decode(errors="replace").strip()[:500]
            diagnostic = {
                "installed": True,
                "path": executable,
                "version": version if process.returncode == 0 else "",
                "returncode": process.returncode,
                "version_check_ok": process.returncode == 0 and bool(version),
            }
            if process.returncode != 0:
                diagnostic["warning"] = f"Version command exited with status {process.returncode}"
                diagnostic["output"] = version
            elif not version:
                diagnostic["warning"] = "Version command produced no output"
            else:
                diagnostic.update(version_details(name, version))
            result["engines"][name] = diagnostic
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["engines"][name] = {"installed": True, "warning": str(exc)}
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
    return result
