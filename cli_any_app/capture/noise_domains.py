from cli_any_app.capture.filters import normalize_domain

NOISE_DOMAIN_PATTERNS = [
    "*.apple.com", "*.icloud.com", "*.mzstatic.com", "*.apple-dns.net",
    "firebaselogging.googleapis.com", "app-measurement.com",
    "*.crashlytics.com", "*.google-analytics.com", "*.googletagmanager.com",
    "*.adjust.com", "*.branch.io", "*.appsflyer.com", "*.amplitude.com",
    "*.mixpanel.com", "*.segment.io", "*.segment.com",
    "*.facebook.com", "*.facebook.net", "*.fbcdn.net", "graph.facebook.com",
    "*.doubleclick.net", "*.googlesyndication.com", "*.googleadservices.com",
    "*.adcolony.com", "*.applovin.com", "*.unity3d.com",
    "*.push.apple.com", "*.firebase.googleapis.com", "fcm.googleapis.com",
    "*.cloudfront.net", "*.akamaized.net", "*.fastly.net",
]


def matches_noise_pattern(domain: str) -> bool:
    domain = normalize_domain(domain)
    for pattern in NOISE_DOMAIN_PATTERNS:
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if domain == pattern[2:] or domain.endswith(suffix):
                return True
        else:
            if domain == pattern:
                return True
    return False
