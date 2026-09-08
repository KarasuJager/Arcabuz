from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from fuzzrank.analysis.baseline import media_type
from fuzzrank.models import Activation, Candidate


def path_tokens(path: str) -> set[str]:
    decoded = unquote(urlsplit(path).path).lower()
    parts = set(re.split(r"[/\.\s]+", decoded))
    return parts | set(re.split(r"[/\.\s_-]+", decoded))


def score(candidate: Candidate, configuration: dict) -> None:
    tokens = path_tokens(candidate.path)
    extension = PurePosixPath(unquote(urlsplit(candidate.path).path)).suffix.lower()
    acts = [Activation("base_score", configuration["base_score"], "Configured starting score")]
    for rule in configuration["rules"]:
        matches = []
        for selector, values in rule["when"].items():
            if selector == "path_tokens":
                matches.append(bool(tokens & {v.lower() for v in values}))
            elif selector == "extensions":
                matches.append(extension in {v.lower() for v in values})
            elif selector == "content_types":
                matches.append(
                    any(
                        fnmatch.fnmatchcase(media_type(candidate.primary), v.lower())
                        for v in values
                    )
                )
            elif selector == "statuses":
                matches.append(candidate.primary.status_code in values)
            elif selector == "signals":
                matches.append(all(candidate.signals.get(v, False) for v in values))
        if all(matches):
            acts.append(Activation(rule["id"], rule["points"], rule["reason"]))
    total = sum(a.points for a in acts)
    capped = max(0, min(100, total))
    if total != capped:
        acts.append(Activation("score_cap", capped - total, "Clamp score to the 0-100 range"))
    candidate.score_reasons = acts
    candidate.score = capped
    candidate.category = (
        "INSPECT NOW"
        if capped >= 90
        else "HIGH"
        if capped >= 70
        else "MEDIUM"
        if capped >= 40
        else "LOW"
    )
