import hashlib
import json
import shutil
from pathlib import Path

import pytest

from fuzzrank.cli import main, prepare_output
from fuzzrank.engines import detect, parse
from fuzzrank.inputs import InputLimits, InputLoader, discover
from fuzzrank.service import Investigation


@pytest.mark.parametrize(
    "filename,engine,count",
    [
        ("ffuf-v2.jsonl", "ffuf", 2),
        ("ffuf-v2.ejson", "ffuf", 1),
        ("ferox-v2.ndjson", "feroxbuster", 2),
        ("gobuster-v3.txt", "gobuster", 3),
    ],
)
def test_realistic_native_variants(fixtures, filename, engine, count):
    data = (fixtures / filename).read_bytes()
    assert detect(data) == engine
    result = parse(data, filename, target="https://fixture.example")
    assert len(result.observations) == count
    assert result.rejected_records == 0


def test_multiple_formats_merge_provenance(fixtures, tmp_path, configuration):
    files = [fixtures / p for p in ["ffuf-v2.jsonl", "ferox-v2.ndjson", "gobuster-v3.txt"]]
    service = Investigation(
        prepare_output(tmp_path / "out"), *configuration, target="https://fixture.example"
    )
    report = service.refresh(files, [])
    assert report.summary["raw_discoveries"] == 7
    assert report.summary["duplicates_merged"] == 4
    user = next(c for c in report.candidates if c.path == "/api/users")
    assert user.engines == ["feroxbuster", "ffuf", "gobuster"]
    assert len({o.source for o in user.observations}) == 3
    assert all(c.score_reasons for c in report.candidates)
    assert all(Path(s["original_path"]).name == s["original_path"] for s in report.sources)


def test_directory_discovery_excludes_generated_and_unrelated_files(fixtures, tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    shutil.copyfile(fixtures / "ffuf.json", incoming / "report.json")
    (incoming / "readme.md").write_text("not results")
    (incoming / "ignored.bin").write_bytes(b"binary")
    (incoming / ".hidden.json").write_bytes(b"invalid")
    nested = incoming / "nested"
    nested.mkdir()
    shutil.copyfile(fixtures / "ferox.jsonl", nested / "ferox.jsonl")
    output = prepare_output(incoming / "generated")
    (output / "input.json").write_bytes(b"invalid")
    assert [p.name for p in discover([incoming])] == ["report.json"]
    assert {p.name for p in discover([incoming], recursive=True)} == {"report.json", "ferox.jsonl"}
    assert len(discover([incoming, incoming / "report.json"])) == 1


def test_directory_cli_combines_formats_and_diagnoses_unknown(fixtures, tmp_path):
    incoming = tmp_path / "inputs"
    incoming.mkdir()
    for name in ("ffuf-v2.jsonl", "ferox-v2.ndjson", "gobuster-v3.txt", "browser.har"):
        shutil.copyfile(fixtures / name, incoming / name)
    (incoming / "unrecognized.json").write_text('{"unrelated":true}')
    output = tmp_path / "out"
    assert (
        main(
            [
                "analyze",
                str(incoming),
                "--target",
                "https://fixture.example",
                "--output",
                str(output),
                "--quiet",
            ]
        )
        == 3
    )
    data = json.loads((output / "report.json").read_text())
    assert data["summary"]["raw_discoveries"] == 12
    assert data["summary"]["duplicates_merged"] == 7
    assert data["summary"]["out_of_scope"] == 1
    assert len(data["sources"]) == 5
    assert data["import_diagnostics"]


def test_generated_json_identified_by_content(fixtures, tmp_path, configuration):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    generated = incoming / "copy.json"
    generated.write_text('{"schema_version":1,"candidates":[]}')
    shutil.copyfile(fixtures / "ffuf.json", incoming / "report.json")
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    report = service.refresh([incoming], [])
    assert not report.partial and report.summary["raw_discoveries"] == 3
    assert any(s["status"] == "ignored-report" for s in report.sources)
    assert any(d["severity"] == "info" for d in report.import_diagnostics)


def test_explicit_and_tagged_baselines(write_bundle, tmp_path, configuration):
    body = "<html>This is the same nonexistent page rendered for missing endpoints.</html>"
    baseline = write_bundle(
        "baseline.json",
        [
            {"url": "https://fixture.example/missing-one", "status_code": 200, "body": body},
            {"url": "https://fixture.example/missing-two", "status_code": 200, "body": body},
        ],
    )
    mixed = write_bundle(
        "mixed.json",
        [
            {"url": "https://fixture.example/a", "status_code": 200, "body": body},
            {"url": "https://fixture.example/b", "status_code": 200, "body": body},
            {
                "url": "https://fixture.example/tagged",
                "status_code": 200,
                "body": body,
                "baseline": True,
            },
        ],
    )
    service = Investigation(prepare_output(tmp_path / "out"), *configuration)
    report = service.refresh([mixed, baseline], [baseline])
    assert len(report.baselines) == 3 and report.summary["raw_discoveries"] == 2
    assert all(c.baseline == "match" for c in report.candidates)
    assert report.summary["noise_suppressed"] == 1
    assert all(c.evidence_quality == "baseline-compared" for c in report.candidates)
    assert report.clusters[0]["observation_count"] == 2
    assert report.clusters[0]["suppression_reasons"]


@pytest.mark.parametrize(
    "setting,value",
    [
        ("file_bytes", 0),
        ("file_bytes", 257 * 1024**2),
        ("total_bytes", -1),
        ("total_bytes", 513 * 1024**2),
        ("records", 100001),
        ("records", True),
        ("files", 0),
        ("files", 10001),
    ],
)
def test_limit_validation(setting, value):
    with pytest.raises(ValueError, match="Input limit"):
        InputLimits(**{setting: value})


def test_record_limit_preserves_sources(fixtures, tmp_path, configuration):
    service = Investigation(
        prepare_output(tmp_path / "out"), *configuration, limits=InputLimits(records=3)
    )
    report = service.refresh([fixtures / "ffuf.json", fixtures / "ferox.jsonl"], [])
    assert report.partial and report.summary["raw_discoveries"] == 3
    assert report.sources[1]["status"] == "limit-excluded"
    for source in report.sources:
        assert (service.loader.output / source["archive"]).exists()


def test_file_count_includes_baselines(fixtures, tmp_path):
    loader = InputLoader(prepare_output(tmp_path / "out"), InputLimits(files=1))
    with pytest.raises(ValueError, match="including baselines"):
        loader.load([fixtures / "ffuf.json"], [fixtures / "ferox.jsonl"])


def test_large_file_rejected_without_deleting_original(fixtures, tmp_path):
    loader = InputLoader(prepare_output(tmp_path / "out"), InputLimits(file_bytes=10))
    source = fixtures / "ffuf.json"
    before = source.read_bytes()
    loaded = loader.load([source], [])
    assert loaded.partial and loaded.diagnostics
    assert source.read_bytes() == before
    assert "byte limit" in loaded.warnings[0]


def test_all_record_errors_retained_in_diagnostics(tmp_path):
    file = tmp_path / "bad.jsonl"
    file.write_text(
        '{"url":"https://fixture.example/a","status":200,"length":1}\n' + '{"status":"bad"}\n' * 75
    )
    loader = InputLoader(prepare_output(tmp_path / "out"))
    result = loader.load([file], [])
    assert result.rejected_records == 75
    assert len([d for d in result.diagnostics if d["severity"] == "error"]) == 75
    assert len(result.warnings) == 31
    assert len(result.observations) == 1


def test_interrupt_during_parse_leaves_attributable_archive(fixtures, tmp_path, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("fuzzrank.inputs.parse", interrupted)
    output = prepare_output(tmp_path / "out")
    with pytest.raises(KeyboardInterrupt):
        InputLoader(output).load([fixtures / "ffuf.json"], [])
    sidecar = json.loads(next((output / "evidence").glob("*.source.json")).read_text())
    data = (output / sidecar["archive"]).read_bytes()
    assert data == (fixtures / "ffuf.json").read_bytes()
    assert sidecar["sha256"] == hashlib.sha256(data).hexdigest()


def test_changed_during_read_is_rejected(fixtures, tmp_path, monkeypatch):
    states = iter([(10, 1, 1), (11, 2, 1)])
    monkeypatch.setattr("fuzzrank.inputs.signature", lambda _: next(states))
    result = InputLoader(prepare_output(tmp_path / "out")).load([fixtures / "ffuf.json"], [])
    assert not result.observations and result.partial
    assert any("changed while" in warning for warning in result.warnings)
    assert result.sources[0]["status"] == "rejected"


def test_body_pool_shared_across_inputs(write_bundle, tmp_path):
    row = {"url": "https://fixture.example/a", "status_code": 200, "body": "Shared content! " * 50}
    files = [write_bundle(f"{n}.json", [row]) for n in range(3)]
    loader = InputLoader(prepare_output(tmp_path / "out"))
    result = loader.load(files, [], retain_last_good=True)
    assert len({id(o.body) for o in result.observations}) == 1
    assert len({id(s.result.observations[0].body) for s in loader.cache.values()}) == 1
