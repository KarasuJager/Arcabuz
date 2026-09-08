import json
from pathlib import Path

import pytest

from fuzzrank.config import load_configuration
from fuzzrank.engines.base import observation


@pytest.fixture
def make_observation():
    def make(path="/api/users", body=None, **overrides):
        row = {
            "url": "https://fixture.example" + path,
            "status_code": 200,
            "content_type": "text/html",
            "body": body,
        }
        row.update(overrides)
        engine = row.pop("engine", "fixture")
        return observation(row, engine=engine, source="fixture", record=1)

    return make


@pytest.fixture
def configuration():
    return load_configuration()


@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def write_bundle(tmp_path):
    def write(name, rows):
        path = tmp_path / name
        path.write_text(json.dumps({"format": "fuzzrank-evidence-v1", "observations": rows}))
        return path

    return write
