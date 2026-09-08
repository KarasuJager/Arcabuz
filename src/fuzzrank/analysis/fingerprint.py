from __future__ import annotations

import hashlib
import heapq
import re
from html.parser import HTMLParser

from fuzzrank.analysis.normalization import VERSION, normalize
from fuzzrank.models import Fingerprint, Observation


class _Title(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self.inside = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.inside = False

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.parts.append(data)


def fingerprint(observation: Observation) -> Fingerprint | None:
    if observation.body is None:
        return None
    raw = observation.body
    normalized, text = normalize(raw, observation.content_type)
    title = None
    if text is not None and "html" in observation.content_type.lower():
        parser = _Title()
        parser.feed(text[:65536])
        title = " ".join("".join(parser.parts).split())[:300] or None
    shingles: frozenset[int] = frozenset()
    if text and len(text) >= 128:
        tokens = re.findall(r"\S+", text)
        values = (
            int.from_bytes(
                hashlib.blake2b(" ".join(tokens[i : i + 5]).encode(), digest_size=8).digest(), "big"
            )
            for i in range(max(0, len(tokens) - 4))
        )
        # Keep the 128 smallest DISTINCT shingles without retaining every body's token hash.
        sample: set[int] = set()
        largest: list[int] = []
        for value in values:
            if value in sample:
                continue
            if len(sample) < 128:
                sample.add(value)
                heapq.heappush(largest, -value)
            elif value < -largest[0]:
                sample.remove(-heapq.heapreplace(largest, -value))
                sample.add(value)
        shingles = frozenset(sample)
    return Fingerprint(
        hashlib.sha256(raw).hexdigest(),
        hashlib.sha256(normalized).hexdigest(),
        len(normalized),
        title,
        shingles,
        not observation.truncated,
        VERSION,
    )


def similarity(left: Fingerprint, right: Fingerprint) -> float:
    if left.normalized_sha256 == right.normalized_sha256:
        return 1.0
    if len(left.shingles) < 12 or len(right.shingles) < 12:
        return 0.0
    return len(left.shingles & right.shingles) / len(left.shingles | right.shingles)


class FingerprintCache:
    def __init__(self):
        self.values: dict[tuple, Fingerprint] = {}

    def get(self, item: Observation) -> Fingerprint | None:
        if item.body is None:
            return None
        key = (item.body, item.content_type, item.truncated)
        if key not in self.values:
            self.values[key] = fingerprint(item)
        return self.values[key]
