"""Data-only rules with strict validation and no expression evaluation."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

SIGNALS = {
    "baseline_match",
    "baseline_near",
    "baseline_different",
    "unique_body",
    "successful_unique",
    "rare_shape",
    "external_redirect",
    "duplicate",
    "conflict",
}
SELECTORS = {"path_tokens", "extensions", "content_types", "statuses", "signals"}


class _StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ValueError("YAML aliases are not supported in configuration")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError("YAML mapping keys must be unique strings")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _yaml(path: Path) -> dict:
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Configuration files must be no larger than 128 KiB")
    try:
        result = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        raise ValueError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("Configuration must be a mapping")
    return result


def validate_rules(data: dict) -> dict:
    if (
        set(data) != {"version", "base_score", "rules"}
        or type(data["version"]) is not int
        or data["version"] != 1
    ):
        raise ValueError("Rules require version: 1, base_score, and rules")
    if type(data["base_score"]) is not int or not 0 <= data["base_score"] <= 100:
        raise ValueError("base_score must be an integer between 0 and 100")
    if not isinstance(data["rules"], list) or len(data["rules"]) > 256:
        raise ValueError("rules must be a list with at most 256 entries")
    seen = set()
    for rule in data["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"id", "points", "reason", "when"}:
            raise ValueError("Each rule requires exactly id, points, reason, and when")
        if not isinstance(rule["id"], str) or not rule["id"] or rule["id"] in seen:
            raise ValueError("Rule ids must be unique nonempty strings")
        seen.add(rule["id"])
        if type(rule["points"]) is not int or not -100 <= rule["points"] <= 100:
            raise ValueError("Rule points must be an integer between -100 and 100")
        if not isinstance(rule["reason"], str) or not rule["reason"].strip():
            raise ValueError("Rule reason must be a nonempty string")
        when = rule["when"]
        if not isinstance(when, dict) or not when or not set(when) <= SELECTORS:
            raise ValueError("Unknown or empty rule selector")
        for selector, values in when.items():
            if not isinstance(values, list) or not values or len(values) > 128:
                raise ValueError("Selector values must be nonempty lists of at most 128 items")
            if selector == "statuses":
                if any(type(v) is not int or not 100 <= v <= 599 for v in values):
                    raise ValueError("statuses must contain HTTP status integers")
            elif any(not isinstance(v, str) or not v for v in values):
                raise ValueError("Selector values must be nonempty strings")
            elif selector == "signals" and not set(values) <= SIGNALS:
                raise ValueError("Unknown signal name")
    return data


def load_configuration(
    profile: str = "generic", rules_path: Path | None = None
) -> tuple[dict, dict]:
    directory = files("fuzzrank")
    custom = Path(profile)
    if custom.suffix.lower() in {".yaml", ".yml"}:
        settings = _yaml(custom)
    else:
        if profile not in {"generic", "web", "api"}:
            raise ValueError("Profile must be generic, web, api, or an explicit YAML path")
        settings = _yaml(Path(str(directory.joinpath("profiles", profile + ".yaml"))))
    allowed = {"name", "description", "extensions", "wordlist_hints", "rule_points"}
    if set(settings) != allowed or not isinstance(settings["name"], str):
        raise ValueError("Invalid profile fields")
    if not isinstance(settings["description"], str):
        raise ValueError("Profile description must be a string")
    for key in ("extensions", "wordlist_hints"):
        if not isinstance(settings[key], list) or any(
            not isinstance(x, str) for x in settings[key]
        ):
            raise ValueError(f"Profile {key} must be a list of strings")
    if not isinstance(settings["rule_points"], dict):
        raise ValueError("Profile rule_points must be a mapping")
    rule_file = rules_path or Path(str(directory.joinpath("rules", "default.yaml")))
    rules = validate_rules(_yaml(rule_file))
    ids = {rule["id"] for rule in rules["rules"]}
    if not set(settings["rule_points"]) <= ids:
        raise ValueError("Profile overrides an unknown rule id")
    for rule in rules["rules"]:
        if rule["id"] in settings["rule_points"]:
            rule["points"] = settings["rule_points"][rule["id"]]
    return settings, validate_rules(rules)
