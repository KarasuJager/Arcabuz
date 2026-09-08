from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from fuzzrank.analysis.baseline import response_shape
from fuzzrank.models import Candidate
from fuzzrank.scope import origin


def cluster(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for item in candidates:
        fp = item.fingerprint
        if fp and fp.complete and fp.normalized_length >= 32 and not item.evidence_conflict:
            key = (
                origin(item.url),
                item.method,
                *response_shape(item.primary),
                fp.normalized_sha256,
            )
        else:
            # Missing/truncated/empty bodies must not turn size/status coincidences into duplicates.
            key = (item.id,)
        digest = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
        item.response_cluster = f"C-{digest}"
        groups[item.response_cluster].append(item)
    for members in groups.values():
        for item in members:
            item.cluster_size = len(members)
    return dict(sorted(groups.items()))


def suppress(groups: dict[str, list[Candidate]]) -> None:
    for members in groups.values():
        ranked = sorted(members, key=lambda c: (-c.score, c.url, c.method))
        representative = ranked[0]
        for item in ranked[1:]:
            if item.evidence_conflict:
                continue
            if item.baseline == "match" and representative.baseline == "match":
                item.suppressed = True
                item.suppression_reason = (
                    "Repeated nonexistent-path baseline; representative retained"
                )
            elif 200 <= item.primary.status_code < 300:
                item.suppressed = True
                item.suppression_reason = "Identical normalized response; representative retained"
            item.signals["duplicate"] = item.suppressed
