from cli_any_app.generation.redactor import has_unredacted_sensitive_data, redact_sensitive_data


def test_redacts_bearer_tokens():
    data = {
        "flows": [{"label": "test", "requests": [{
            "request_headers": {"Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."},
            "request_body": {"email": "user@example.com", "password": "secret123"},
            "response_headers": {},
            "response_body": {"token": "eyJ0eXAi...", "refresh_token": "abc123def"},
        }]}]
    }
    result = redact_sensitive_data(data)
    req = result["flows"][0]["requests"][0]
    assert req["request_headers"]["Authorization"] == "Bearer <REDACTED>"
    assert req["request_body"]["password"] == "<REDACTED>"
    assert req["response_body"]["token"] == "<REDACTED_TOKEN>"
    assert req["response_body"]["refresh_token"] == "<REDACTED_TOKEN>"


def test_preserves_non_sensitive_data():
    data = {
        "flows": [{"label": "test", "requests": [{
            "request_headers": {"Content-Type": "application/json"},
            "request_body": {"name": "John", "age": 30},
            "response_headers": {"Content-Type": "application/json"},
            "response_body": {"id": 1, "name": "John"},
        }]}]
    }
    result = redact_sensitive_data(data)
    req = result["flows"][0]["requests"][0]
    assert req["request_body"]["name"] == "John"
    assert req["response_body"]["id"] == 1


def test_does_not_mutate_original():
    data = {"flows": [{"label": "test", "requests": [{
        "request_headers": {}, "response_headers": {},
        "request_body": {"password": "secret"},
        "response_body": {},
    }]}]}
    result = redact_sensitive_data(data)
    assert data["flows"][0]["requests"][0]["request_body"]["password"] == "secret"
    assert result["flows"][0]["requests"][0]["request_body"]["password"] == "<REDACTED>"


def test_preflight_ignores_redacted_placeholders():
    data = {
        "flows": [{"requests": [{
            "request_body": {
                "patient_id": "<PATIENT_ID:1234567890>",
                "email": "<EMAIL:abcdef1234>",
                "phone": "<PHONE:abcdef1234>",
            }
        }]}]
    }

    assert has_unredacted_sensitive_data(data) is False


def test_preflight_flags_unredacted_sensitive_data():
    data = {"value": "patient_id=ABCD1234"}

    assert has_unredacted_sensitive_data(data) is True
