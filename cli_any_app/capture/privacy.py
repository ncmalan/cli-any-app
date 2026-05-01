from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from cryptography.fernet import Fernet

from cli_any_app.config import settings

REDACTED = "<REDACTED>"
REDACTED_TOKEN = "<REDACTED_TOKEN>"

SENSITIVE_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-csrf-token",
    "proxy-authorization",
}

SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "code",
    "id_token",
    "key",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
}

SENSITIVE_BODY_KEYS = {
    "access_token",
    "address",
    "api_key",
    "apikey",
    "authorization",
    "card_number",
    "cookie",
    "cvv",
    "date_of_birth",
    "diagnosis",
    "dob",
    "email",
    "first_name",
    "last_name",
    "medication",
    "mrn",
    "passwd",
    "password",
    "patient",
    "patient_id",
    "phone",
    "refresh_token",
    "secret",
    "session_token",
    "ssn",
    "token",
}

TEXTUAL_CONTENT_TYPES = (
    "application/graphql",
    "application/json",
    "application/x-www-form-urlencoded",
    "application/xml",
    "multipart/form-data",
    "text/",
)

BINARY_CONTENT_MARKERS = (
    "application/octet-stream",
    "application/pdf",
    "application/protobuf",
    "application/x-protobuf",
    "audio/",
    "font/",
    "image/",
    "video/",
)

PHI_PATTERNS = [
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "<EMAIL>"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<SSN>"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "<PHONE>"),
    (re.compile(r"\b(?:19|20)\d{2}[-/](?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12]\d|3[01])\b"), "<DATE>"),
    (re.compile(r"\b(?:MRN|patient[_\s-]?id)[-:=]?\s*[A-Z0-9-]{4,}\b", re.I), "<PATIENT_ID>"),
]


def stable_placeholder(label: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"<{label}:{digest}>"


def _private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _data_key_path() -> Path:
    return settings.secrets_dir / "payload-data.key"


def _get_payload_fernet() -> Fernet:
    path = _data_key_path()
    if path.exists():
        return Fernet(path.read_bytes())
    key = Fernet.generate_key()
    _private_write(path, key)
    return Fernet(key)


def encrypt_payload(value: str | None) -> str | None:
    if value is None:
        return None
    token = _get_payload_fernet().encrypt(value.encode("utf-8", errors="replace"))
    return token.decode("ascii")


def decrypt_payload(value: str | None) -> str | None:
    if value is None:
        return None
    return _get_payload_fernet().decrypt(value.encode("ascii")).decode("utf-8", errors="replace")


def body_size(value: str | None) -> int:
    if value is None:
        return 0
    return len(value.encode("utf-8", errors="replace"))


def body_hash(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def headers_size(headers: dict[str, Any]) -> int:
    return len(json.dumps(headers, sort_keys=True, default=str).encode("utf-8"))


def is_binary_content(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    if not lowered:
        return False
    if any(marker in lowered for marker in BINARY_CONTENT_MARKERS):
        return True
    return not any(marker in lowered for marker in TEXTUAL_CONTENT_TYPES)


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


def redact_url(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    safe_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in SENSITIVE_QUERY_KEYS or "token" in lowered or "secret" in lowered:
            safe_pairs.append((key, REDACTED))
        else:
            safe_pairs.append((key, redact_string(value)))
    redacted_query = urlencode(safe_pairs, doseq=True)
    safe_path = quote(redact_string(unquote(parsed.path or "/")), safe="/:<>")
    redacted_path = urlunsplit(("", "", safe_path, redacted_query, ""))
    redacted_full = urlunsplit((parsed.scheme, parsed.netloc, safe_path, redacted_query, ""))
    return parsed.netloc, redacted_path, redacted_full


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_key_value(key, nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact_key_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in SENSITIVE_BODY_KEYS or "token" in lowered or "secret" in lowered:
        return REDACTED_TOKEN if "token" in lowered else REDACTED
    return redact_value(value)


def redact_string(value: str) -> str:
    redacted = value
    for pattern, label in PHI_PATTERNS:
        redacted = pattern.sub(lambda match: stable_placeholder(label.strip("<>"), match.group(0)), redacted)
    return redacted


def redact_body_text(value: str | None, content_type: str) -> str | None:
    if value is None:
        return None
    if is_binary_content(content_type):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return redact_string(value)
    return json.dumps(redact_value(parsed), sort_keys=True)


def has_sensitive_plaintext(value: Any) -> bool:
    if value is None:
        return False
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    if REDACTED in text or "<EMAIL:" in text or "<PHONE:" in text:
        return False
    return any(pattern.search(text) for pattern, _ in PHI_PATTERNS)


def encode_metadata_blob(value: Any) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).decode("ascii")
