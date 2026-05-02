from __future__ import annotations

import copy
import json
import re
from typing import Any

from cli_any_app.capture.privacy import (
    REDACTED,
    REDACTED_TOKEN,
    PHI_PATTERNS,
    redact_headers as _redact_headers,
    redact_key_value as _redact_key_value,
    redact_query_string,
    redact_string as _redact_string,
    redact_url as _redact_capture_url,
    redact_value as _redact_value,
)

REDACTED_PLACEHOLDER = re.compile(r"<[A-Z_]+:[0-9a-f]{10}>")


def redact_sensitive_data(data: dict) -> dict:
    result = copy.deepcopy(data)
    for flow in result.get("flows", []):
        for req in flow.get("requests", []):
            req["request_headers"] = redact_headers(req.get("request_headers", {}))
            req["response_headers"] = redact_headers(req.get("response_headers", {}))
            if "url" in req:
                req["url"] = redact_url(req["url"])
            if "query" in req:
                req["query"] = redact_query(req["query"])
            if "path" in req:
                req["path"] = redact_string(req["path"])
            req["request_body"] = redact_value(req.get("request_body"))
            req["response_body"] = redact_value(req.get("response_body"))
    return result


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    return _redact_headers(headers)


def redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None:
        return _redact_key_value(key, value)
    return _redact_value(value)


def redact_string(value: str) -> str:
    return _redact_string(value)


def redact_url(url: str) -> str:
    _host, _path, redacted_url = _redact_capture_url(url)
    return redacted_url


def redact_query(query: str) -> str:
    return redact_query_string(query)


def has_unredacted_sensitive_data(data: dict) -> bool:
    text = json.dumps(data, default=str)
    text = REDACTED_PLACEHOLDER.sub("", text)
    text = text.replace(REDACTED_TOKEN, "").replace(REDACTED, "")
    return any(pattern.search(text) for pattern, _label in PHI_PATTERNS)
