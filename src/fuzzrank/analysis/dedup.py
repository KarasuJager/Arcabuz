from __future__ import annotations

import hashlib
from collections import defaultdict
from urllib.parse import urlsplit

from fuzzrank.analysis.fingerprint import FingerprintCache
from fuzzrank.models import Candidate, Observation
from fuzzrank.scope import canonical_url


def deduplicate(
    observations: list[Observation], cache: FingerprintCache | None = None
) -> list[Candidate]:
    cache = cache or FingerprintCache()
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for item in observations:
        groups[(item.method, canonical_url(item.url))].append(item)
    results = []
    for (method, url), items in sorted(groups.items()):
        # Prefer complete body evidence, then a stable tie breaker, never input order.
        items.sort(
            key=lambda o: (
                o.body is None or o.truncated,
                o.body is None,
                o.status_code,
                o.engine,
                o.source,
                o.record,
            )
        )
        primary = items[0]
        prints = [cache.get(o) for o in items]
        shapes = {
            (o.status_code, o.content_type.split(";")[0].strip().lower(), o.location) for o in items
        }
        statuses = {o.status_code for o in items}
        known_types = {shape[1] for shape in shapes if shape[1]}
        hashes = {fp.normalized_sha256 for fp in prints if fp and fp.complete}
        conflict = len(statuses) > 1 or len(known_types) > 1 or len(hashes) > 1
        conflict |= len({o.location for o in items if 300 <= o.status_code < 400}) > 1
        parts = urlsplit(url)
        path = parts.path + ("?" + parts.query if parts.query else "")
        results.append(
            Candidate(
                id=hashlib.sha256(f"{method} {url}".encode()).hexdigest()[:20],
                method=method,
                url=url,
                path=path,
                observations=items,
                primary=primary,
                fingerprint=prints[0],
                evidence_conflict=conflict,
            )
        )
    return results
