import ipaddress
from urllib.parse import urlparse

API_CONTENT_TYPES = {
    "application/json", "application/x-protobuf", "application/x-www-form-urlencoded",
    "application/xml", "text/xml", "application/graphql", "application/grpc", "application/msgpack",
}

NON_API_CONTENT_TYPES = {
    "image/", "font/", "text/html", "text/css", "application/javascript",
    "text/javascript", "video/", "audio/", "application/octet-stream",
}


def is_api_request(content_type: str, url: str) -> bool:
    ct = content_type.split(";")[0].strip().lower() if content_type else ""
    if any(ct.startswith(nac) for nac in NON_API_CONTENT_TYPES):
        return False
    if ct in API_CONTENT_TYPES:
        return True
    path = urlparse(url).path.lower()
    static_extensions = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico"}
    if any(path.endswith(ext) for ext in static_extensions):
        return False
    return True


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().lower()
    if not domain:
        return ""

    bracketless = domain[1:-1] if domain.startswith("[") and domain.endswith("]") else domain
    try:
        return str(ipaddress.ip_address(bracketless))
    except ValueError:
        pass

    parsed = urlparse(domain if "://" in domain else f"//{domain}")
    try:
        hostname = parsed.hostname
    except ValueError:
        return domain
    return (hostname or domain).lower()


def extract_domain(url: str) -> str:
    return normalize_domain(urlparse(url).hostname or "")
