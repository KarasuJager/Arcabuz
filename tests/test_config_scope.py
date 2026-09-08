import copy

import pytest
import yaml

from fuzzrank.config import load_configuration, validate_rules
from fuzzrank.scope import Scope, canonical_url


@pytest.mark.parametrize("profile", ["generic", "web", "api"])
def test_builtin_profiles_are_valid(profile):
    settings, rules = load_configuration(profile)
    assert settings["name"] == profile
    assert rules["rules"]


@pytest.mark.parametrize(
    "change",
    [
        {"points": "25"},
        {"points": True},
        {"points": 101},
        {"reason": ""},
        {"when": {"execute": ["something"]}},
        {"when": {"signals": ["unknown"]}},
        {"when": {"statuses": ["200"]}},
        {"when": {}},
        {"when": {"path_tokens": []}},
    ],
)
def test_bad_rules_rejected(configuration, change):
    _, rules = configuration
    rules = copy.deepcopy(rules)
    rules["rules"][0].update(change)
    with pytest.raises(ValueError):
        validate_rules(rules)


def test_duplicate_rule_ids_rejected(configuration):
    _, rules = configuration
    rules["rules"].append(rules["rules"][0].copy())
    with pytest.raises(ValueError, match="unique"):
        validate_rules(rules)


def test_custom_profile_is_data_only(tmp_path):
    settings, _ = load_configuration("web")
    settings.update(name="php", extensions=[".php"], rule_points={"functionality": 21})
    path = tmp_path / "php.yaml"
    path.write_text(yaml.safe_dump(settings))
    profile, rules = load_configuration(str(path))
    assert profile["name"] == "php"
    assert next(r for r in rules["rules"] if r["id"] == "functionality")["points"] == 21


def test_unsafe_yaml_tags_rejected(tmp_path):
    path = tmp_path / "evil.yaml"
    path.write_text("!!python/object/apply:os.system ['echo unsafe']")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_configuration(str(path))


@pytest.mark.parametrize(
    "content",
    [
        "name: one\nname: two",
        "name: &cycle {again: *cycle}",
        "{[complex, key]: value}",
    ],
)
def test_ambiguous_yaml_rejected(tmp_path, content):
    path = tmp_path / "ambiguous.yaml"
    path.write_text(content)
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_configuration(str(path))


@pytest.mark.parametrize(
    "url",
    [
        "https://fixture.example:99999/",
        "https://fixture.example:0/",
        "file:///tmp/test",
        "https://user:pass@fixture.example/",
        "https://fixture.example\\@other.example/",
        "https://fixture.example/\r\n",
        "//fixture.example/path",
        "https://%65xample.test/",
    ],
)
def test_unsafe_or_ambiguous_urls_rejected(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_exact_origin_scope(tmp_path):
    path = tmp_path / "scope.txt"
    path.write_text("# Additional authorized imports\nhttps://api.fixture.example:8443\n")
    scope = Scope.load("https://fixture.example", path)
    assert scope.contains("https://fixture.example/a")
    assert scope.contains("https://api.fixture.example:8443/a")
    assert not scope.contains("http://fixture.example/a")
    assert not scope.contains("https://sub.fixture.example/a")
    assert not scope.contains("https://api.fixture.example/a")


@pytest.mark.parametrize(
    "entry", ["*.fixture.example", "https://fixture.example/path", "https://fixture.example/?a=1"]
)
def test_scope_rejects_wildcards_and_paths(tmp_path, entry):
    path = tmp_path / "scope.txt"
    path.write_text(entry)
    with pytest.raises(ValueError):
        Scope.load("https://fixture.example", path)
