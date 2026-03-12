import copy

SENSITIVE_HEADER_KEYS = {"authorization", "cookie", "set-cookie", "x-api-key"}
SENSITIVE_BODY_KEYS = {
    "password", "passwd", "secret", "token", "access_token",
    "refresh_token", "api_key", "apikey", "session_token",
    "credit_card", "card_number", "cvv", "ssn",
}


def redact_sensitive_data(data: dict) -> dict:
    result = copy.deepcopy(data)
    for flow in result.get("flows", []):
        for req in flow.get("requests", []):
            _redact_headers(req.get("request_headers", {}))
            _redact_headers(req.get("response_headers", {}))
            _redact_body(req, "request_body")
            _redact_body(req, "response_body")
    return result


def _redact_headers(headers: dict):
    for key in list(headers.keys()):
        if key.lower() in SENSITIVE_HEADER_KEYS:
            val = headers[key]
            if isinstance(val, str) and val.lower().startswith("bearer "):
                headers[key] = "Bearer <REDACTED>"
            else:
                headers[key] = "<REDACTED>"


def _redact_body(req: dict, field: str):
    body = req.get(field)
    if isinstance(body, dict):
        _redact_dict(body)


def _redact_dict(d: dict):
    for key in list(d.keys()):
        if key.lower() in SENSITIVE_BODY_KEYS:
            if "token" in key.lower():
                d[key] = "<REDACTED_TOKEN>"
            else:
                d[key] = "<REDACTED>"
        elif isinstance(d[key], dict):
            _redact_dict(d[key])
