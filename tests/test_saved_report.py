import copy
import json

import pytest

from fuzzrank.pipeline import analyze
from fuzzrank.reporting import json_report, load_report
from fuzzrank.scope import Scope


@pytest.fixture
def document(make_observation, configuration):
    body = "A sufficiently detailed response for evidence fingerprints and comparison."
    rows = [make_observation("/admin", body), make_observation("/admin-copy", body)]
    return json_report.serializable(
        analyze(rows, [], Scope.load("https://fixture.example"), *configuration)
    )


def save(tmp_path, document):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_saved_roundtrip_preserves_every_v1_field(document, tmp_path):
    report = load_report.read(save(tmp_path, document))
    assert json_report.serializable(report) == document
    assert report.candidates[0].primary.body is report.candidates[1].primary.body


@pytest.mark.parametrize(
    "corruption",
    [
        "id",
        "primary",
        "score",
        "cluster",
        "member",
        "size",
        "reference",
        "summary",
        "path",
        "url",
        "engine",
        "body",
        "fingerprint",
        "missing",
        "version",
    ],
)
def test_saved_report_rejects_corrupt_contract(document, tmp_path, corruption):
    candidate = document["candidates"][0]
    if corruption == "id":
        document["candidates"][1]["id"] = candidate["id"]
    elif corruption == "primary":
        candidate["primary"]["status_code"] = 500
    elif corruption == "score":
        candidate["score_reasons"][0]["points"] += 1
    elif corruption == "cluster":
        document["clusters"][0]["representative"] = "missing"
    elif corruption == "member":
        document["clusters"][0]["members"][0] = "missing"
    elif corruption == "size":
        document["clusters"][0]["size"] += 1
    elif corruption == "reference":
        candidate["response_cluster"] = "unknown"
    elif corruption == "summary":
        document["summary"]["raw_discoveries"] += 1
    elif corruption == "path":
        candidate["path"] = "/other"
    elif corruption == "url":
        candidate["url"] = "file:///private.txt"
    elif corruption == "engine":
        candidate["engines"] = ["invented"]
    elif corruption == "body":
        candidate["primary"]["body"]["data"] = "!!!!"
    elif corruption == "fingerprint":
        candidate["fingerprint"]["raw_sha256"] = "0" * 64
    elif corruption == "missing":
        del document["metadata"]
    elif corruption == "version":
        document["schema_version"] = 9
    with pytest.raises(ValueError):
        load_report.read(save(tmp_path, document))


def test_saved_report_duplicate_keys_and_size_limit(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text('{"format":1,"format":2}')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_report.read(path)
    monkeypatch.setattr(load_report, "MAX_REPORT_BYTES", 4)
    with pytest.raises(ValueError, match="byte limit"):
        load_report.read(path)


def test_saved_report_never_follows_references(document, tmp_path, monkeypatch):
    from pathlib import Path

    document["metadata"]["evidence_root"] = "https://outside.example/"
    document["sources"] = [
        {
            "id": "external",
            "original_path": "anything",
            "archive": "../../secret",
            "sha256": "0" * 64,
            "bytes": 0,
            "role": "discovery",
            "status": "accepted",
        }
    ]
    path = save(tmp_path, document)
    original = Path.open

    def guarded(self, *args, **kwargs):
        assert self == path or self.name == "report-v1.schema.json"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    restored = load_report.read(path)
    assert restored.sources == document["sources"]


def test_saved_report_unknown_additive_fields_are_tolerated(document, tmp_path):
    changed = copy.deepcopy(document)
    changed["future_field"] = {"untrusted": "data"}
    changed["candidates"][0]["future_field"] = 1
    assert json_report.serializable(load_report.read(save(tmp_path, changed))) == document


def test_saved_report_does_not_rescore(document, tmp_path, monkeypatch):
    import fuzzrank.pipeline

    def forbidden(*args, **kwargs):
        pytest.fail("Saved report must not reanalyze its evidence")

    monkeypatch.setattr(fuzzrank.pipeline, "analyze", forbidden)
    assert load_report.read(save(tmp_path, document)).candidates
