"""Read the shared V1 report contract without rescoring or following evidence references."""

from __future__ import annotations

import base64
import hashlib
from collections import Counter
from dataclasses import fields, replace
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from fuzzrank.engines.base import MAX_BODY_BYTES, BodyPool, decode_json, observation, read_input
from fuzzrank.models import Activation, Candidate, Fingerprint, Observation, Report
from fuzzrank.scope import canonical_url

MAX_REPORT_BYTES = 256 * 1024**2


def _known(model, row):
    return {field.name: row[field.name] for field in fields(model) if field.name in row}


def read(path: Path) -> Report:
    # Optional desktop dependency; importing the base CLI never requires jsonschema or Qt.
    from jsonschema import Draft202012Validator

    document = decode_json(read_input(path, MAX_REPORT_BYTES))
    schema = decode_json(files("fuzzrank").joinpath("schemas/report-v1.schema.json").read_bytes())
    error = next(Draft202012Validator(schema).iter_errors(document), None)
    if error:
        location = "/".join(map(str, error.absolute_path)) or "report"
        raise ValueError(f"Invalid saved report at {location[:200]} ({error.validator})")
    total = sum(len(c["observations"]) for c in document["candidates"])
    total += len(document["baselines"]) + len(document["excluded"])
    if total > 100_000:
        raise ValueError("Saved report exceeds 100000 observations")
    pool = BodyPool()

    def restore(row) -> Observation:
        values = _known(Observation, row)
        body = row["body"]
        if body is not None:
            if len(body["data"]) > (MAX_BODY_BYTES + 2) // 3 * 4:
                raise ValueError("Saved report body exceeds the 1 MiB limit")
            try:
                decoded = base64.b64decode(body["data"], validate=True)
            except ValueError as exc:
                raise ValueError("Saved report contains an invalid base64 body") from exc
            if len(decoded) > MAX_BODY_BYTES:
                raise ValueError("Saved report body exceeds the 1 MiB limit")
            values["body"] = decoded
        item = observation(
            {**values, "body": None},
            engine=row["engine"],
            source=row["source"],
            record=row["record"],
        )
        return pool.intern(
            replace(
                item,
                **{
                    **values,
                    "evidence_notes": tuple(row["evidence_notes"]),
                    "header_items": tuple(tuple(pair) for pair in row["header_items"]),
                },
            )
        )

    candidates, identities = [], set()
    for row in document["candidates"]:
        if row["id"] in identities:
            raise ValueError("Saved report contains duplicate candidate IDs")
        identities.add(row["id"])
        canonical_url(row["url"])
        observations = [restore(o) for o in row["observations"]]
        primary = restore(row["primary"])
        if primary not in observations:
            raise ValueError("Saved report primary is not one of its observations")
        parts = urlsplit(row["url"])
        path = parts.path + ("?" + parts.query if parts.query else "")
        if row["path"] != path or any(
            (o.method, canonical_url(o.url)) != (row["method"], row["url"]) for o in observations
        ):
            raise ValueError("Saved report candidate/observation identities disagree")
        if row["engines"] != sorted({o.engine for o in observations}):
            raise ValueError("Saved report provenance disagrees with observations")
        reasons = [Activation(**_known(Activation, reason)) for reason in row["score_reasons"]]
        if sum(reason.points for reason in reasons) != row["score"]:
            raise ValueError("Saved report score explanation does not sum to its score")
        fp = row["fingerprint"]
        if fp:
            if primary.body is None or hashlib.sha256(primary.body).hexdigest() != fp["raw_sha256"]:
                raise ValueError("Saved report raw fingerprint disagrees with evidence")
            fp = Fingerprint(**{**_known(Fingerprint, fp), "shingles": frozenset(fp["shingles"])})
        candidates.append(
            Candidate(
                **{
                    **_known(Candidate, row),
                    "observations": observations,
                    "primary": primary,
                    "fingerprint": fp,
                    "score_reasons": reasons,
                }
            )
        )
    members = set()
    cluster_ids = set()
    for cluster in document["clusters"]:
        if cluster["id"] in cluster_ids or cluster["representative"] not in cluster["members"]:
            raise ValueError("Saved report has invalid cluster identity or representative")
        cluster_ids.add(cluster["id"])
        for candidate_id in cluster["members"]:
            if candidate_id not in identities or candidate_id in members:
                raise ValueError("Saved report has invalid cluster membership")
            members.add(candidate_id)
        if cluster["size"] != len(cluster["members"]):
            raise ValueError("Saved report cluster size does not match membership")
    if members != identities:
        raise ValueError("Saved report has unclustered candidates")
    lookup = {cluster["id"]: set(cluster["members"]) for cluster in document["clusters"]}
    if any(
        c.id not in lookup.get(c.response_cluster, set())
        or c.cluster_size != len(lookup[c.response_cluster])
        for c in candidates
    ):
        raise ValueError("Saved report candidate/cluster references disagree")
    # Validate saved totals, without re-running classification or changing conclusions.
    included = sum(len(c.observations) for c in candidates)
    counts = Counter(c.category for c in candidates if not c.suppressed)
    expected = {
        "raw_discoveries": included + len(document["excluded"]),
        "out_of_scope": len(document["excluded"]),
        "duplicates_merged": included - len(candidates),
        "unique_endpoints": len(candidates),
        "noise_suppressed": sum(c.suppressed for c in candidates),
        "unique_candidates": sum(not c.suppressed for c in candidates),
        "inspect_now": counts["INSPECT NOW"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
    }
    if any(document["summary"][key] != value for key, value in expected.items()):
        raise ValueError("Saved report summary disagrees with its evidence")
    return Report(
        **{
            **_known(Report, document),
            "candidates": candidates,
            "baselines": [restore(o) for o in document["baselines"]],
            "excluded": [restore(o) for o in document["excluded"]],
        }
    )
