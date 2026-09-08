"""Install a wheel in a fresh virtual environment and exercise only local workflows."""

import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path


def smoke(wheel_dir: Path, output: Path, gui: bool = False) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    wheels = list(wheel_dir.resolve().glob("fuzzrank-*.whl"))
    if len(wheels) != 1:
        raise ValueError("Select a directory containing exactly one FuzzRank wheel")
    venv_dir = output / "venv"
    venv.create(venv_dir, with_pip=True)
    scripts = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    executable = scripts / ("fuzzrank.exe" if os.name == "nt" else "fuzzrank")
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    def checked(argv):
        subprocess.run(
            [str(arg) for arg in argv],
            check=True,
            cwd=output,
            env=environment,
            timeout=180,
            shell=False,
        )

    checked([python, "-m", "pip", "install", "--no-cache-dir", wheels[0]])
    checked([python, "-m", "pip", "check"])
    checked(
        [
            python,
            "-c",
            "import fuzzrank,sys; from pathlib import Path; "
            "assert Path(sys.prefix) in Path(fuzzrank.__file__).parents; "
            "from importlib.resources import files; "
            "assert files('fuzzrank').joinpath('schemas/report-v1.schema.json').is_file(); "
            "print('Wheel module and schema verified')",
        ]
    )
    checked([executable, "--help"])
    checked([executable, "--version"])
    checked(
        [python, "-c", "import importlib.util; assert importlib.util.find_spec('PySide6') is None"]
    )
    checked([executable, "doctor", "--json"])
    missing_gui = subprocess.run(
        [str(python), "-m", "fuzzrank.gui"],
        cwd=output,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
    assert (
        missing_gui.returncode == 1 and "Desktop dependencies are unavailable" in missing_gui.stderr
    )
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    checked(
        [
            executable,
            "analyze",
            fixture,
            "--target",
            "https://fixture.example",
            "--profile",
            "api",
            "--output",
            "analysis",
            "--quiet",
        ]
    )
    checked(
        [
            executable,
            "watch",
            fixture,
            "--target",
            "https://fixture.example",
            "--max-updates",
            "1",
            "--debounce",
            ".05",
            "--poll-interval",
            ".05",
            "--output",
            "watch",
            "--quiet",
        ]
    )
    checked([executable, "demo", "--output", "demo", "--quiet"])
    for folder in ["analysis", "watch/generations/000001", "demo"]:
        root = output / folder
        document = json.loads((root / "report.json").read_text())
        assert all(c["score_reasons"] for c in document["candidates"])
        assert (root / "report.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    print("Installed wheel: help, version, doctor, directory/HAR analysis, watch and demo PASS")
    if gui:
        checked([python, "-m", "pip", "install", str(wheels[0]) + "[gui]"])
        checked([python, "-m", "pip", "check"])
        gui_executable = scripts / ("fuzzrank-gui.exe" if os.name == "nt" else "fuzzrank-gui")
        environment["QT_QPA_PLATFORM"] = "offscreen"
        checked(
            [
                python,
                "-c",
                "from importlib.resources import files; "
                "from PySide6.QtWidgets import QApplication; "
                "from fuzzrank.gui import brand; app = QApplication([]); "
                "assert files('fuzzrank.gui').joinpath('assets/fuzzrank-logo.png').is_file(); "
                "assert not brand.icon().isNull(); assert not brand.mark().isNull(); "
                "print('Installed approved logo and native icon verified')",
            ]
        )
        checked(
            [
                gui_executable,
                "--demo",
                "--output",
                "gui-demo",
                "--settings",
                "gui.ini",
                "--quit-after-load",
                "--screenshot",
                "gui-demo.png",
            ]
        )
        checked(
            [
                gui_executable,
                "--open-report",
                "analysis/report.json",
                "--settings",
                "gui.ini",
                "--quit-after-load",
                "--screenshot",
                "gui-report.png",
            ]
        )
        document = json.loads((output / "gui-demo/report.json").read_text())
        assert document["summary"]["raw_discoveries"] == 35
        assert document["summary"]["noise_suppressed"] == 22
        assert all(c["score_reasons"] for c in document["candidates"])
        for image in ("gui-demo.png", "gui-report.png"):
            assert (output / image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        print("Installed optional GUI: native launch, demo, saved report and screenshots PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true", help="Also install and verify the GUI extra")
    args = parser.parse_args()
    try:
        smoke(args.wheel_dir, args.output, args.gui)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
