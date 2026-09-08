"""Synthetic stress invariants; deliberately no machine-dependent timing assertions."""

import hashlib
import json

from fuzzrank.analysis.fingerprint import FingerprintCache
from fuzzrank.engines import parse
from fuzzrank.pipeline import analyze
from fuzzrank.scope import Scope


def test_twenty_thousand_records_pool_bodies_and_cluster(configuration):
    count = 20_000
    body = "<html><p>The same custom application fallback content appears here.</p></html>"
    rows = [
        {
            "url": f"https://fixture.example/path-{i // 2}",
            "status_code": 200,
            "body": body,
            "engine": "first" if i % 2 else "second",
        }
        for i in range(count)
    ]
    data = json.dumps({"format": "fuzzrank-evidence-v1", "observations": rows}).encode()
    result = parse(data, "synthetic")
    assert len({id(o.body) for o in result.observations}) == 1
    report = analyze(result.observations, [], Scope.load("https://fixture.example"), *configuration)
    assert report.summary["raw_discoveries"] == count
    assert report.summary["duplicates_merged"] == count // 2
    assert report.summary["noise_suppressed"] == count // 2 - 1
    assert report.metadata["fingerprint_cache_entries"] == 1
    assert report.clusters[0]["observation_count"] == count
    assert report.clusters[0]["engines"] == ["first", "second"]
    assert all(sum(r.points for r in c.score_reasons) == c.score for c in report.candidates)


def test_fingerprint_cache_distinguishes_type_and_completeness(make_observation):
    cache = FingerprintCache()
    a = make_observation(body="Exact same body", content_type="text/plain")
    b = make_observation(body="Exact same body", content_type="text/html")
    c = make_observation(body="Exact same body", content_type="text/plain", truncated=True)
    assert cache.get(a) is cache.get(a)
    assert cache.get(a) is not cache.get(b)
    assert cache.get(c).complete is False
    assert len(cache.values) == 3


def test_ten_thousand_jsonl_records_preserve_record_diagnostics():
    good = b'{"url":"https://fixture.example/a","status":200,"length":1}\n'
    data = (good * 4999) + b"{invalid}\n" + (good * 5000)
    result = parse(data, "fixture.jsonl", "ffuf")
    assert len(result.observations) == 9999 and result.rejected_records == 1
    assert result.diagnostics[0]["record"] == 5000


def test_bounded_shingle_sample_matches_exact_bottom_set(make_observation):
    tokens = [str(n) for n in range(3000)] * 2
    values = {
        int.from_bytes(
            hashlib.blake2b(" ".join(tokens[i : i + 5]).encode(), digest_size=8).digest(), "big"
        )
        for i in range(len(tokens) - 4)
    }
    item = make_observation(body=" ".join(tokens), content_type="text/plain")
    assert FingerprintCache().get(item).shingles == frozenset(sorted(values)[:128])
