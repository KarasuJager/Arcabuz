import hashlib

import pytest

from fuzzrank.analysis.fingerprint import fingerprint, similarity
from fuzzrank.analysis.normalization import normalize


@pytest.mark.parametrize("key", ["request_id", "correlation_id", "nonce", "csrf_token"])
def test_json_labeled_tokens_normalize(key):
    a = ('{"' + key + '":"a123456789abcdef0000","user":"alice"}').encode()
    b = ('{"user":"alice","' + key + '":"b123456789abcdef1111"}').encode()
    assert normalize(a, "application/json")[0] == normalize(b, "application/json")[0]
    assert a != b


def test_timestamp_only_labeled():
    a = b'{"timestamp":"2026-01-01T00:00:00Z","created":"2020-01-01T00:00:00Z"}'
    b = b'{"timestamp":"2026-02-01T00:00:00Z","created":"2020-01-01T00:00:00Z"}'
    assert normalize(a, "application/json") == normalize(b, "application/json")
    assert normalize(a.replace(b"2020-01", b"2020-02"), "application/json") != normalize(
        a, "application/json"
    )


@pytest.mark.parametrize(
    "left,right",
    [
        (
            b'{"user_id":"aaaaaaaa-bbbb-cccc-dddd-111111111111"}',
            b'{"user_id":"aaaaaaaa-bbbb-cccc-dddd-222222222222"}',
        ),
        (b'{"count":100}', b'{"count":101}'),
        (b'{"nonce":"short1"}', b'{"nonce":"short2"}'),
        (b'{"balance":1.01}', b'{"balance":"1.01"}'),
        (b'{"balance":1e2}', b'{"balance":"1e2"}'),
        (b'{"a":1,"a":2}', b'{"a":2}'),
    ],
)
def test_meaningful_json_values_preserved(left, right):
    assert normalize(left, "application/json")[0] != normalize(right, "application/json")[0]


@pytest.mark.parametrize(
    "media,body",
    [
        ("image/png", b"\x89PNG\x00request_id=abcdefghijklmnop"),
        ("text/html", b"\xff\xfeinvalid utf-8"),
        ("", b"nonce=abcdefghijklmnop"),
        ("application/json", b'{"n":NaN}'),
        ("application/json", b'{"n":1.2}'),
    ],
)
def test_unknown_binary_or_ambiguous_data_unchanged(media, body):
    assert normalize(body, media)[0] == body


def test_html_fingerprint_keeps_raw_and_escapable_title(make_observation):
    a = make_observation(body='<title>&lt;Test&gt;</title><p nonce="aaaaaaaaaaaaaaaa">same</p>')
    b = make_observation(body='<title>&lt;Test&gt;</title><p nonce="bbbbbbbbbbbbbbbb">same</p>')
    x, y = fingerprint(a), fingerprint(b)
    assert x.raw_sha256 == hashlib.sha256(a.body).hexdigest()
    assert x.raw_sha256 != y.raw_sha256
    assert x.normalized_sha256 == y.normalized_sha256
    assert x.title == "<Test>"
    assert similarity(x, y) == 1.0
    assert a.body.endswith(b"</p>")


def test_whitespace_and_unlabeled_text_preserved():
    for body in [b"<pre>a  b</pre>", b"2026-01-01T00:00:00Z", b"missing /requested/path"]:
        assert normalize(body, "text/html")[0] == body


def test_missing_and_truncated_bodies(make_observation):
    assert fingerprint(make_observation()) is None
    assert not fingerprint(make_observation(body="partial", truncated=True)).complete


def test_similarity_signature_is_bounded(make_observation):
    one = fingerprint(make_observation(body=" ".join(f"word{i}" for i in range(5000))))
    two = fingerprint(make_observation(body=" ".join(f"other{i}" for i in range(5000))))
    assert len(one.shingles) == 128
    assert similarity(one, two) < 0.3
