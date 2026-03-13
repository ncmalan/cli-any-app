import json
import re
from urllib.parse import urlparse

VOLATILE_HEADER_KEYS = {
    "date",
    "x-request-id",
    "x-trace-id",
    "cf-ray",
    "server-timing",
}


def normalize_session_data(raw: dict) -> dict:
    app_name = raw["app_name"]
    flows = []
    all_paths = []

    for flow_data in raw["flows"]:
        requests = []
        for req in flow_data["requests"]:
            if not req.get("is_api", True):
                continue
            parsed = urlparse(req["url"])
            base_url = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port and parsed.port not in (80, 443):
                base_url += f":{parsed.port}"

            request_headers = _parse_json(req.get("request_headers", "{}"))
            response_headers = _parse_json(req.get("response_headers", "{}"))
            request_body = _parse_json_or_raw(req.get("request_body"))
            response_body = _parse_json_or_raw(req.get("response_body"))

            _strip_volatile_headers(request_headers)
            _strip_volatile_headers(response_headers)

            path = parsed.path
            query = parsed.query
            all_paths.append(path)

            normalized = {
                "method": req["method"],
                "base_url": base_url,
                "path": path,
                "query": query,
                "request_headers": request_headers,
                "request_body": request_body,
                "status_code": req["status_code"],
                "response_headers": response_headers,
                "response_body": response_body,
            }
            requests.append(normalized)

        if requests:
            flows.append({"label": flow_data["label"], "requests": requests})

    endpoint_patterns = _detect_url_patterns(all_paths)
    return {"app": app_name, "flows": flows, "endpoint_patterns": endpoint_patterns}


def _detect_url_patterns(paths: list[str]) -> dict[str, list[str]]:
    patterns: dict[str, list[str]] = {}
    for path in paths:
        parts = path.strip("/").split("/")
        key = tuple("{id}" if re.match(r"^\d+$", p) else p for p in parts)
        pattern = "/" + "/".join(key)
        if pattern not in patterns:
            patterns[pattern] = []
        patterns[pattern].append(path)
    return patterns


def _parse_json(val):
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_json_or_raw(val):
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def _strip_volatile_headers(headers: dict):
    for key in list(headers.keys()):
        if key.lower() in VOLATILE_HEADER_KEYS:
            headers.pop(key, None)
