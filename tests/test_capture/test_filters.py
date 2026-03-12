from cli_any_app.capture.filters import is_api_request, extract_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern


# --- Filter tests ---

def test_json_api_is_detected():
    assert is_api_request("application/json", "https://api.example.com/v1/users") is True


def test_image_is_not_api():
    assert is_api_request("image/png", "https://cdn.example.com/photo.png") is False


def test_static_js_is_not_api():
    assert is_api_request("application/javascript", "https://example.com/bundle.js") is False


def test_protobuf_is_api():
    assert is_api_request("application/x-protobuf", "https://api.example.com/rpc") is True


def test_form_post_is_api():
    assert is_api_request("application/x-www-form-urlencoded", "https://api.example.com/login") is True


def test_extract_domain():
    assert extract_domain("https://api.uber.com/v1/users?id=1") == "api.uber.com"


# --- Noise domain tests ---

def test_apple_is_noise():
    assert matches_noise_pattern("gateway.icloud.com") is True


def test_firebase_is_noise():
    assert matches_noise_pattern("firebaselogging.googleapis.com") is True


def test_app_api_is_not_noise():
    assert matches_noise_pattern("api.uber.com") is False
