from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urljoin

from fuzzrank import __version__
from fuzzrank.analysis.baseline import BaselineIndex
from fuzzrank.analysis.clustering import cluster, suppress
from fuzzrank.analysis.dedup import deduplicate
from fuzzrank.analysis.fingerprint import FingerprintCache
from fuzzrank.analysis.scoring import score
from fuzzrank.models import Observation, Report
from fuzzrank.scope import Scope


def analyze(
    observations: list[Observation],
    baselines: list[Observation],
    scope: Scope,
    profile: dict,
    rules: dict,
    warnings: list[str] | None = None,
) -> Report:
    warnings = list(warnings or [])
    included = [o for o in observations if scope.contains(o.url)]
    excluded = [o for o in observations if not scope.contains(o.url)]
    eligible_baselines = [o for o in baselines if scope.contains(o.url)]
    if len(eligible_baselines) != len(baselines):
        warnings.append("Out-of-scope baseline records retained but not used for comparison")
    cache = FingerprintCache()
    candidates = deduplicate(included, cache)
    groups = cluster(candidates)
    baseline_index = BaselineIndex(eligible_baselines, cache)
    shapes = Counter((o.primary.status_code, o.primary.content_length) for o in candidates)
    for item in candidates:
        item.baseline, item.baseline_similarity = baseline_index.compare(item)
        fp = item.fingerprint
        item.evidence_gaps = []
        if fp is None:
            item.evidence_gaps.append("Response body unavailable; body-based rules cannot activate")
        elif not fp.complete:
            item.evidence_gaps.append("Incomplete body; exact suppression disabled")
        if item.baseline == "unavailable":
            item.evidence_gaps.append("Reliable baseline comparison unavailable")
        if item.evidence_conflict:
            item.evidence_gaps.append("Observations disagree; automatic suppression disabled")
        item.evidence_quality = (
            "baseline-compared"
            if not item.evidence_gaps
            else "body-only"
            if fp and fp.complete and not item.evidence_conflict
            else "limited"
        )
        unique = bool(
            fp
            and fp.complete
            and fp.normalized_length >= 32
            and item.cluster_size == 1
            and not item.evidence_conflict
        )
        external = False
        if 300 <= item.primary.status_code < 400 and item.primary.location:
            try:
                external = not scope.contains(urljoin(item.url, item.primary.location))
            except ValueError:
                warnings.append(
                    f"Invalid redirect destination for {item.id}; destination not followed"
                )
        item.signals = {
            "baseline_match": item.baseline == "match",
            "baseline_near": item.baseline == "near",
            "baseline_different": item.baseline == "different",
            "unique_body": unique,
            "successful_unique": unique and 200 <= item.primary.status_code < 300,
            "rare_shape": (
                len(candidates) >= 20
                and item.primary.content_length is not None
                and shapes[(item.primary.status_code, item.primary.content_length)] <= 2
            ),
            "external_redirect": external,
            "duplicate": False,
            "conflict": item.evidence_conflict,
        }
        score(item, rules)
    suppress(groups)
    for item in candidates:
        score(item, rules)
    candidates.sort(key=lambda c: (c.suppressed, -c.score, c.url, c.method))
    kept = [c for c in candidates if not c.suppressed]
    counts = Counter(c.category for c in kept)
    unavailable = sum(c.baseline == "unavailable" for c in candidates)
    if unavailable:
        warnings.append(f"{unavailable} candidates lack reliable baseline comparison evidence")
    if excluded:
        warnings.append(f"{len(excluded)} out-of-scope observations retained in excluded evidence")
    clusters = []
    for cluster_id, members in groups.items():
        representative = min(members, key=lambda c: (c.suppressed, -c.score, c.url, c.method))
        clusters.append(
            {
                "id": cluster_id,
                "size": len(members),
                "members": sorted(c.id for c in members),
                "representative": representative.id,
                "suppressed": sum(c.suppressed for c in members),
                "observation_count": sum(len(c.observations) for c in members),
                "statuses": sorted({o.status_code for c in members for o in c.observations}),
                "engines": sorted({engine for c in members for engine in c.engines}),
                "content_types": sorted({c.primary.content_type for c in members}),
                "length_range": [min(lengths), max(lengths)]
                if (
                    lengths := [
                        c.primary.content_length
                        for c in members
                        if c.primary.content_length is not None
                    ]
                )
                else None,
                "suppression_reasons": sorted(
                    {c.suppression_reason for c in members if c.suppression_reason}
                ),
                "baseline_matches": sum(c.baseline == "match" for c in members),
                "classification": (
                    "Probable wildcard/custom-404 response"
                    if all(c.baseline == "match" for c in members)
                    else "Identical normalized responses"
                    if len(members) > 1
                    else "Single response / no safe grouping evidence"
                ),
            }
        )
    summary = {
        "raw_discoveries": len(observations),
        "out_of_scope": len(excluded),
        "in_scope_observations": len(included),
        "duplicates_merged": len(included) - len(candidates),
        "unique_endpoints": len(candidates),
        "noise_suppressed": sum(c.suppressed for c in candidates),
        "unique_candidates": len(kept),
        "inspect_now": counts["INSPECT NOW"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
    }
    report = Report(
        1,
        scope.target,
        sorted(scope.origins),
        profile["name"],
        summary,
        candidates,
        baselines,
        warnings,
        clusters,
        {"profile": profile, "rules": rules},
        excluded,
    )
    report.metadata = {
        "tool": "FuzzRank",
        "tool_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "schema": "urn:fuzzrank:report:1",
        "body_encoding": "base64",
        "fingerprint_cache_entries": len(cache.values),
    }
    return report
