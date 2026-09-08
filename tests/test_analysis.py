from dataclasses import replace

import pytest

from fuzzrank.analysis.baseline import BaselineIndex
from fuzzrank.analysis.clustering import cluster
from fuzzrank.analysis.dedup import deduplicate
from fuzzrank.analysis.scoring import path_tokens, score
from fuzzrank.pipeline import analyze
from fuzzrank.scope import Scope

PAGE = "<html><title>Missing</title><p>The requested page does not exist.</p></html>"


def test_distinct_paths_required_for_baseline(make_observation):
    a = make_observation("/missing1", PAGE)
    b = make_observation("/missing2", PAGE)
    candidate = deduplicate([make_observation("/noise", PAGE)])[0]
    assert BaselineIndex([a, a]).compare(candidate)[0] == "unavailable"
    assert BaselineIndex([a, b]).compare(candidate) == ("match", 1.0)


@pytest.mark.parametrize(
    "change",
    [
        {"status_code": 403},
        {"content_type": "application/json"},
        {"location": "/other"},
        {"body": "<p>A completely different response for authorized staff only.</p>"},
    ],
)
def test_status_alone_never_defines_baseline(make_observation, change):
    baseline = [make_observation("/a", PAGE), make_observation("/b", PAGE)]
    values = {"body": PAGE, **change}
    c = deduplicate([make_observation("/admin", **values)])[0]
    assert BaselineIndex(baseline).compare(c)[0] == "different"


@pytest.mark.parametrize(
    "change",
    [
        {"method": "POST"},
        {"url": "https://elsewhere.example/noise"},
        {"truncated": True},
        {"body": None},
    ],
)
def test_baseline_not_applied_without_compatible_evidence(make_observation, change):
    baseline = [make_observation("/api/a", PAGE), make_observation("/api/b", PAGE)]
    values = {"body": PAGE, **change}
    candidate = deduplicate([make_observation("/api/noise", **values)])[0]
    assert BaselineIndex(baseline).compare(candidate)[0] == "unavailable"


def test_subtree_baselines_and_specific_ancestor(make_observation):
    baseline = [make_observation("/api/a", PAGE), make_observation("/api/b", PAGE)]
    c = deduplicate([make_observation("/web/noise", PAGE)])[0]
    assert BaselineIndex(baseline).compare(c)[0] == "unavailable"
    deep = deduplicate([make_observation("/api/deep/noise", PAGE)])[0]
    assert BaselineIndex(baseline).compare(deep)[0] == "match"


def test_empty_or_short_baselines_cannot_suppress(make_observation):
    baseline = [make_observation("/a", ""), make_observation("/b", "")]
    c = deduplicate([make_observation("/admin", "")])[0]
    assert BaselineIndex(baseline).compare(c)[0] == "unavailable"


def test_cross_engine_dedup_preserves_evidence(make_observation):
    one = make_observation("/api/users", engine="ffuf")
    two = make_observation("/api/users", PAGE, engine="feroxbuster")
    candidates = deduplicate([one, two])
    assert len(candidates) == 1
    assert candidates[0].engines == ["feroxbuster", "ffuf"]
    assert len(candidates[0].observations) == 2
    assert candidates[0].primary == two
    assert not candidates[0].evidence_conflict


def test_query_order_method_and_path_case_not_merged(make_observation):
    paths = ["/A", "/a", "/a?x=1&y=2", "/a?y=2&x=1", "/a/"]
    records = [make_observation(p) for p in paths] + [make_observation("/a", method="POST")]
    assert len(deduplicate(records)) == 6


def test_canonical_host_and_default_port_merged(make_observation):
    one = make_observation(url="https://FIXTURE.example:443/a#section")
    two = make_observation(url="https://fixture.example/a")
    assert len(deduplicate([one, two])) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"status_code": 403},
        {"body": PAGE + "different"},
        {"content_type": "text/plain"},
    ],
)
def test_conflicts_disable_suppression(make_observation, configuration, change):
    profile, rules = configuration
    values = {"body": PAGE, **change}
    observations = [
        make_observation("/a", PAGE),
        make_observation("/a", **values),
        make_observation("/b", PAGE),
    ]
    result = analyze(observations, [], Scope.load("https://fixture.example"), profile, rules)
    a = next(c for c in result.candidates if c.path == "/a")
    assert a.evidence_conflict and not a.suppressed
    assert a.cluster_size == 1
    assert any(r.rule_id == "observation_conflict" for r in a.score_reasons)


def test_metadata_only_responses_are_not_grouped(make_observation):
    cs = deduplicate([make_observation(f"/p{i}", content_length=100) for i in range(100)])
    assert len(cluster(cs)) == 100


def test_exact_clustering_scales_and_is_order_independent(make_observation):
    rows = [make_observation(f"/route{i:05d}", PAGE) for i in range(4000)]
    a, b = deduplicate(rows), deduplicate(list(reversed(rows)))
    assert list(cluster(a)) == list(cluster(b))
    assert len(cluster(a)) == 1
    assert a[0].cluster_size == 4000


def test_wildcard_keeps_one_representative(make_observation, configuration):
    profile, rules = configuration
    rows = [make_observation(f"/path-{i}", PAGE) for i in range(50)]
    baseline = [make_observation("/not-found1", PAGE), make_observation("/not-found2", PAGE)]
    result = analyze(rows, baseline, Scope.load("https://fixture.example"), profile, rules)
    assert result.summary["noise_suppressed"] == 49
    assert result.summary["unique_candidates"] == 1
    assert all(c.score == 0 for c in result.candidates)
    assert all(c.baseline == "match" for c in result.candidates)
    assert result.clusters[0]["classification"].startswith("Probable wildcard")
    assert sum(len(c.observations) for c in result.candidates) == 50


def test_ordinary_authorization_duplicates_stay_visible(make_observation, configuration):
    profile, rules = configuration
    rows = [
        make_observation("/admin", PAGE, status_code=403),
        make_observation("/internal", PAGE, status_code=403),
    ]
    result = analyze(rows, [], Scope.load("https://fixture.example"), profile, rules)
    assert all(not c.suppressed for c in result.candidates)


def test_duplicate_representative_uses_highest_priority(make_observation, configuration):
    profile, rules = configuration
    rows = [make_observation("/plain", PAGE), make_observation("/admin/export", PAGE)]
    result = analyze(rows, [], Scope.load("https://fixture.example"), profile, rules)
    assert not result.candidates[0].suppressed
    assert result.candidates[0].path == "/admin/export"
    assert result.candidates[1].suppressed


def test_explanations_sum_to_score_including_cap(make_observation, configuration):
    _, rules = configuration
    c = deduplicate(
        [make_observation("/swagger/admin/api/export", content_type="application/json")]
    )[0]
    c.signals = {"unique_body": True, "successful_unique": True, "baseline_different": True}
    score(c, rules)
    assert c.score == 100
    assert sum(x.points for x in c.score_reasons) == c.score
    assert c.category == "INSPECT NOW"


def test_200_status_alone_gets_no_bonus(make_observation, configuration):
    _, rules = configuration
    c = deduplicate([make_observation("/plain")])[0]
    score(c, rules)
    assert c.score == 10
    assert len(c.score_reasons) == 1


def test_keywords_do_not_match_substrings_or_query_values():
    tokens = path_tokens("/myadministrator?next=/admin")
    assert "admin" not in tokens
    assert "api-docs" in path_tokens("/v1/api-docs.json")
    assert "admin" in path_tokens("/%61dmin/export")


def test_out_of_scope_retained_and_redirect_flagged(make_observation, configuration):
    profile, rules = configuration
    rows = [
        make_observation("/redirect", location="https://other.example/", status_code=302),
        make_observation(url="https://other.example/admin"),
    ]
    result = analyze(rows, [], Scope.load("https://fixture.example"), profile, rules)
    assert result.summary["out_of_scope"] == 1
    assert len(result.excluded) == 1
    assert result.candidates[0].signals["external_redirect"]


def test_rare_shape_requires_enough_evidence(make_observation, configuration):
    profile, rules = configuration
    rows = [make_observation(f"/p{i}", content_length=100) for i in range(19)]
    special = make_observation("/special", content_length=500, status_code=403)
    report = analyze(rows + [special], [], Scope.load("https://fixture.example"), profile, rules)
    assert next(c for c in report.candidates if c.path == "/special").signals["rare_shape"]
    report = analyze([special], [], Scope.load("https://fixture.example"), profile, rules)
    assert not report.candidates[0].signals["rare_shape"]


def test_approximate_match_never_suppresses(make_observation, configuration):
    # Alter one token in a large response so sampled shingle similarity stays high.
    body = " ".join(f"token{i}" for i in range(300))
    changed = body.replace("token150", "different150")
    rows = [make_observation("/near", changed)]
    baseline = [make_observation("/a", body), make_observation("/b", body)]
    profile, rules = configuration
    report = analyze(rows, baseline, Scope.load("https://fixture.example"), profile, rules)
    assert report.candidates[0].baseline == "near"
    assert not report.candidates[0].suppressed


def test_truncated_clusters_are_singletons(make_observation):
    a = make_observation("/a", PAGE, truncated=True)
    b = replace(a, url="https://fixture.example/b")
    assert len(cluster(deduplicate([a, b]))) == 2
