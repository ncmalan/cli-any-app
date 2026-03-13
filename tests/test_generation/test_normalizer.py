from cli_any_app.generation.normalizer import normalize_session_data


def test_normalize_groups_by_flow():
    raw = {
        "app_name": "test-app",
        "flows": [{
            "label": "login",
            "requests": [{
                "method": "POST",
                "url": "https://api.example.com/v1/auth/login",
                "request_headers": '{"Content-Type": "application/json"}',
                "request_body": '{"email": "test@test.com", "password": "secret"}',
                "status_code": 200,
                "response_headers": '{"Content-Type": "application/json"}',
                "response_body": '{"token": "abc123", "user": {"id": 1}}',
                "content_type": "application/json",
                "is_api": True,
            }],
        }],
    }
    result = normalize_session_data(raw)
    assert result["app"] == "test-app"
    assert len(result["flows"]) == 1
    assert result["flows"][0]["label"] == "login"
    req = result["flows"][0]["requests"][0]
    assert req["method"] == "POST"
    assert req["path"] == "/v1/auth/login"
    assert req["base_url"] == "https://api.example.com"


def test_normalize_strips_volatile_headers():
    raw = {
        "app_name": "test",
        "flows": [{"label": "test", "requests": [{
            "method": "GET", "url": "https://api.example.com/test",
            "request_headers": '{"Date": "Wed, 01 Jan 2025", "X-Request-Id": "abc123", "Content-Type": "application/json"}',
            "request_body": None, "status_code": 200,
            "response_headers": '{"Date": "Wed, 01 Jan 2025", "Server-Timing": "total;dur=50"}',
            "response_body": '{}', "content_type": "application/json", "is_api": True,
        }]}],
    }
    result = normalize_session_data(raw)
    req = result["flows"][0]["requests"][0]
    assert "Date" not in req["request_headers"]
    assert "X-Request-Id" not in req["request_headers"]
    assert "Content-Type" in req["request_headers"]
    assert "Date" not in req["response_headers"]
    assert "Server-Timing" not in req["response_headers"]


def test_normalize_detects_url_patterns():
    raw = {
        "app_name": "test",
        "flows": [{"label": "browse", "requests": [
            {"method": "GET", "url": "https://api.example.com/v1/items/123",
             "request_headers": "{}", "request_body": None, "status_code": 200,
             "response_headers": "{}", "response_body": '{"id": 123}',
             "content_type": "application/json", "is_api": True},
            {"method": "GET", "url": "https://api.example.com/v1/items/456",
             "request_headers": "{}", "request_body": None, "status_code": 200,
             "response_headers": "{}", "response_body": '{"id": 456}',
             "content_type": "application/json", "is_api": True},
        ]}],
    }
    result = normalize_session_data(raw)
    assert "/v1/items/{id}" in result["endpoint_patterns"]


def test_normalize_filters_non_api():
    raw = {
        "app_name": "test",
        "flows": [{"label": "test", "requests": [
            {"method": "GET", "url": "https://api.example.com/data",
             "request_headers": "{}", "request_body": None, "status_code": 200,
             "response_headers": "{}", "response_body": "{}",
             "content_type": "application/json", "is_api": True},
            {"method": "GET", "url": "https://cdn.example.com/image.png",
             "request_headers": "{}", "request_body": None, "status_code": 200,
             "response_headers": "{}", "response_body": "",
             "content_type": "image/png", "is_api": False},
        ]}],
    }
    result = normalize_session_data(raw)
    assert len(result["flows"][0]["requests"]) == 1
