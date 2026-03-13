import subprocess
import signal
from pathlib import Path
from cli_any_app.config import settings


class ProxyManager:
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.active_session_id: str | None = None
        self.active_port: int | None = None

    @property
    def addon_path(self) -> str:
        return str(Path(__file__).parent / "addon.py")

    def start(self, session_id: str, port: int | None = None) -> int:
        proxy_port = port or settings.proxy_port
        if self.process and self.process.poll() is None:
            if self.active_session_id == session_id:
                return self.active_port or proxy_port
            raise RuntimeError(f"Proxy already running for session {self.active_session_id}")
        server_url = f"http://127.0.0.1:{settings.port}"
        self.process = subprocess.Popen(
            ["mitmdump", "--listen-port", str(proxy_port), "-s", self.addon_path,
             "--set", f"server_url={server_url}", "--set", f"capture_session_id={session_id}",
             "--set", "connection_strategy=lazy"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.active_session_id = session_id
        self.active_port = proxy_port
        return proxy_port

    def stop(self, session_id: str | None = None):
        if (
            session_id
            and self.process
            and self.process.poll() is None
            and self.active_session_id != session_id
        ):
            raise RuntimeError(f"Proxy is running for session {self.active_session_id}")
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.active_session_id = None
        self.active_port = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def owns_session(self, session_id: str) -> bool:
        return self.is_running and self.active_session_id == session_id


proxy_manager = ProxyManager()
