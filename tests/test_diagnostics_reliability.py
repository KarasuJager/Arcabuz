"""Version-check failures are diagnostics, never scan execution."""

import pytest

from fuzzrank.cli import main
from fuzzrank.doctor import inspect


@pytest.mark.parametrize("returncode,output", [(2, b"bad option"), (0, b"")])
def test_failed_version_check_is_not_displayed_as_success(monkeypatch, returncode, output):
    class Child:
        def __init__(self):
            self.returncode = returncode

        def communicate(self, timeout=None):
            return output, None

        def poll(self):
            return self.returncode

    commands = []

    def create(argv, **kwargs):
        commands.append((argv, kwargs))
        return Child()

    monkeypatch.setattr("fuzzrank.doctor.shutil.which", lambda name: f"/fixture/{name}")
    monkeypatch.setattr("fuzzrank.doctor.subprocess.Popen", create)
    diagnostics = inspect()
    assert len(commands) == 3
    assert all(isinstance(argv, list) and kwargs["shell"] is False for argv, kwargs in commands)
    for diagnostic in diagnostics["engines"].values():
        assert diagnostic["installed"]
        assert diagnostic["version"] == ""
        assert diagnostic["warning"]
        assert not diagnostic["version_check_ok"]
        assert diagnostic["returncode"] == returncode


def test_version_command_launch_failure_is_reported(monkeypatch):
    def failed(*args, **kwargs):
        raise OSError("fixture executable cannot be launched")

    monkeypatch.setattr("fuzzrank.doctor.shutil.which", lambda name: f"/fixture/{name}")
    monkeypatch.setattr("fuzzrank.doctor.subprocess.Popen", failed)
    diagnostics = inspect()
    assert all("cannot be launched" in item["warning"] for item in diagnostics["engines"].values())


def test_cancellation_cleans_active_version_process(monkeypatch, capsys):
    class Child:
        returncode = None
        killed = False
        drained = False

        def communicate(self, timeout=None):
            if timeout is not None:
                raise KeyboardInterrupt
            self.drained = True
            return b"", None

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    child = Child()
    monkeypatch.setattr("fuzzrank.doctor.shutil.which", lambda name: f"/fixture/{name}")
    monkeypatch.setattr("fuzzrank.doctor.subprocess.Popen", lambda *args, **kwargs: child)
    assert main(["doctor"]) == 130
    assert child.killed and child.drained
    assert "Interrupted" in capsys.readouterr().err
