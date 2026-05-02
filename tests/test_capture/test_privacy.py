import hashlib

from cli_any_app.capture.privacy import body_hash, stable_placeholder


def test_stable_placeholder_uses_keyed_digest():
    value = "555-123-4567"

    first = stable_placeholder("PHONE", value)
    second = stable_placeholder("PHONE", value)
    unkeyed_digest = hashlib.sha256(value.encode()).hexdigest()[:10]

    assert first == second
    assert first.startswith("<PHONE:")
    assert unkeyed_digest not in first


def test_body_hash_uses_keyed_digest():
    value = '{"dob":"1970-01-01"}'

    first = body_hash(value)
    second = body_hash(value)
    unkeyed_digest = hashlib.sha256(value.encode()).hexdigest()

    assert first == second
    assert first != unkeyed_digest
    assert body_hash(None) is None
