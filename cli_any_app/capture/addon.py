"""mitmproxy addon - loaded by mitmdump: mitmdump -s addon.py --set server_url=http://localhost:8000"""
import json
import urllib.request
from mitmproxy import http, ctx


class CaptureAddon:
    def __init__(self):
        self.server_url = "http://localhost:8000"
        self.session_id = ""

    def load(self, loader):
        loader.add_option("server_url", str, "http://localhost:8000", "FastAPI server URL")
        loader.add_option("capture_session_id", str, "", "Session ID to capture for")

    def configure(self, updated):
        if "server_url" in updated:
            self.server_url = ctx.options.server_url
        if "capture_session_id" in updated:
            self.session_id = ctx.options.capture_session_id

    def response(self, flow: http.HTTPFlow):
        if not self.session_id:
            return
        try:
            request = flow.request
            response = flow.response
            if response is None:
                return
            content_type = response.headers.get("content-type", "")
            payload = {
                "session_id": self.session_id,
                "method": request.method,
                "url": request.pretty_url,
                "request_headers": dict(request.headers),
                "request_body": request.get_text(strict=False),
                "status_code": response.status_code,
                "response_headers": dict(response.headers),
                "response_body": response.get_text(strict=False),
                "content_type": content_type,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.server_url}/api/internal/capture",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            ctx.log.warn(f"cli-any-app capture error: {e}")


addons = [CaptureAddon()]
