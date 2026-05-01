from __future__ import annotations

import copy
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cli_any_app.capture.privacy import (
    REDACTED,
    REDACTED_TOKEN,
    SENSITIVE_BODY_KEYS,
    SENSITIVE_HEADER_KEYS,
    SENSITIVE_QUERY_KEYS,
    PHI_PATTERNS,
    stable_placeholder,
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
    redacted: dict[str, Any] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in SENSITIVE_HEADER_KEYS or "token" in lowered or "secret" in lowered:
            if isinstance(value, str) and value.lower().startswith("bearer "):
                redacted[key] = f"Bearer {REDACTED}"
            else:
                redacted[key] = REDACTED
        else:
            redacted[key] = redact_value(value)
    return redacted


def redact_value(value: Any, key: str | None = None) -> Any:
    if key:
        lowered = key.lower()
        if lowered in SENSITIVE_BODY_KEYS or "token" in lowered or "secret" in lowered:
            return REDACTED_TOKEN if "token" in lowered else REDACTED
    if isinstance(value, dict):
        return {child_key: redact_value(child_value, child_key) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact_string(value: str) -> str:
    redacted = value
    for pattern, label in PHI_PATTERNS:
        name = label.strip("<>")
        redacted = pattern.sub(lambda match: stable_placeholder(name, match.group(0)), redacted)
    return redacted


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    query = redact_query(parsed.query)
    return urlunsplit((parsed.scheme, _safe_netloc(parsed), redact_string(parsed.path), query, ""))


def _safe_netloc(parsed) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None:
        return f"{host}:{port}"
    return host


def redact_query(query: str) -> str:
    pairs = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in SENSITIVE_QUERY_KEYS or "token" in lowered or "secret" in lowered:
            pairs.append((key, REDACTED))
        else:
            pairs.append((key, redact_string(value)))
    return urlencode(pairs, doseq=True)


def has_unredacted_sensitive_data(data: dict) -> bool:
    text = json.dumps(data, default=str)
    text = REDACTED_PLACEHOLDER.sub("", text)
    text = text.replace(REDACTED_TOKEN, "").replace(REDACTED, "")
    return any(pattern.search(text) for pattern, _label in PHI_PATTERNS)
