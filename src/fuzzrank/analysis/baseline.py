"""Baseline sets are supplied evidence; nothing here contacts their URLs."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit

from fuzzrank.analysis.fingerprint import FingerprintCache, similarity
from fuzzrank.models import Candidate, Fingerprint, Observation
from fuzzrank.scope import canonical_url, origin


def media_type(observation: Observation) -> str:
    return observation.content_type.split(";", 1)[0].strip().lower()


def response_shape(observation: Observation) -> tuple:
    return observation.status_code, media_type(observation), observation.location


class BaselineIndex:
    def __init__(
        self, observations: list[Observation], cache: FingerprintCache | None = None
    ) -> None:
        cache = cache or FingerprintCache()
        groups: dict[tuple, list[tuple[Observation, Fingerprint]]] = defaultdict(list)
        for item in observations:
            fp = cache.get(item)
            if not fp or not fp.complete or fp.normalized_length < 32:
                continue
            parent = urlsplit(item.url).path.rsplit("/", 1)[0] + "/"
            key = (
                origin(item.url),
                item.method,
                parent,
                response_shape(item),
                fp.normalized_sha256,
            )
            groups[key].append((item, fp))
        self.scopes: dict[tuple, list[tuple[Observation, Fingerprint]]] = defaultdict(list)
        for key, items in groups.items():
            # Two repeated requests to the SAME path are not independent missing-path evidence.
            if len({urlsplit(canonical_url(o.url)).path for o, _ in items}) >= 2:
                self.scopes[key[:3]].append(items[0])
        # Bound comparison work even for adversarial baseline files.
        if any(len(items) > 32 for items in self.scopes.values()):
            raise ValueError("Too many baseline variants: maximum 32 per origin/method/path prefix")

    def compare(self, candidate: Candidate) -> tuple[str, float | None]:
        fp = candidate.fingerprint
        if candidate.evidence_conflict or not fp or not fp.complete:
            return "unavailable", None
        path = urlsplit(candidate.url).path
        # Walk ancestors instead of scanning every baseline prefix for each candidate.
        parent = path.rsplit("/", 1)[0] + "/"
        examples = None
        while True:
            examples = self.scopes.get((origin(candidate.url), candidate.method, parent))
            if examples or parent == "/":
                break
            parent = parent.rstrip("/").rsplit("/", 1)[0] + "/"
        if not examples:
            return "unavailable", None
        best = 0.0
        for observation, reference in examples:
            if response_shape(candidate.primary) != response_shape(observation):
                continue
            score = similarity(fp, reference)
            best = max(best, score)
            if fp.normalized_sha256 == reference.normalized_sha256:
                return "match", 1.0
        if best >= 0.90:
            return "near", round(best, 4)
        if best <= 0.30:
            return "different", round(best, 4)
        return "uncertain", round(best, 4)
