"""Evidence is immutable; conclusions are separate and reproducible."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Observation:
    engine: str
    method: str
    url: str
    status_code: int
    content_length: int | None = None
    word_count: int | None = None
    line_count: int | None = None
    content_type: str = ""
    location: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timestamp: str | float | None = None
    body: bytes | None = None
    truncated: bool = False
    source: str = ""
    record: int = 0
    baseline: bool = False
    body_source: str = "capture"
    evidence_notes: tuple[str, ...] = ()
    header_items: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Fingerprint:
    raw_sha256: str
    normalized_sha256: str
    normalized_length: int
    title: str | None
    shingles: frozenset[int]
    complete: bool
    normalization: str


@dataclass(frozen=True)
class Activation:
    rule_id: str
    points: int
    reason: str


@dataclass
class Candidate:
    id: str
    method: str
    url: str
    path: str
    observations: list[Observation]
    primary: Observation
    fingerprint: Fingerprint | None = None
    response_cluster: str = ""
    cluster_size: int = 1
    baseline: str = "unavailable"
    baseline_similarity: float | None = None
    score: int = 0
    category: str = "LOW"
    score_reasons: list[Activation] = field(default_factory=list)
    suppressed: bool = False
    suppression_reason: str | None = None
    signals: dict[str, bool] = field(default_factory=dict)
    evidence_conflict: bool = False
    evidence_quality: str = "limited"
    evidence_gaps: list[str] = field(default_factory=list)

    @property
    def engines(self) -> list[str]:
        return sorted({o.engine for o in self.observations})


@dataclass
class ImportResult:
    observations: list[Observation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejected_records: int = 0
    ignored_records: int = 0
    diagnostics: list[dict] = field(default_factory=list)


@dataclass
class Report:
    schema_version: int
    target: str
    scope: list[str]
    profile: str
    summary: dict[str, int]
    candidates: list[Candidate]
    baselines: list[Observation]
    warnings: list[str]
    clusters: list[dict]
    configuration: dict
    excluded: list[Observation] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    partial: bool = False
    format: str = "fuzzrank-report"
    schema_revision: str = "1.0.0"
    metadata: dict = field(default_factory=dict)
    import_diagnostics: list[dict] = field(default_factory=list)
