import hashlib

from cli_any_app.capture.privacy import body_hash, has_sensitive_plaintext, stable_placeholder


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


def test_sensitive_plaintext_ignores_redaction_placeholders():
    value = {
        "patient_id": "<PATIENT_ID:1234567890>",
        "date": "<DATE:abcdef1234>",
        "email": "<EMAIL:abcdef1234>",
        "masked": "<REDACTED>",
    }

    assert has_sensitive_plaintext(value) is False


def test_sensitive_plaintext_detects_real_phi_with_redaction_markers():
    value = {
        "masked": "<REDACTED>",
        "patient_id": "patient_id=ABC12345",
    }

    assert has_sensitive_plaintext(value) is True
