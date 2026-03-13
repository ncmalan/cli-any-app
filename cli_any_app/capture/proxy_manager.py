import subprocess
import signal
from pathlib import Path
from cli_any_app.config import settings


class ProxyManager:
    def __init__(self):
        self.process: subprocess.Popen | None = None

    @property
    def addon_path(self) -> str:
        return str(Path(__file__).parent / "addon.py")

    def start(self, session_id: str, port: int | None = None) -> int:
        if self.process and self.process.poll() is None:
            raise RuntimeError("Proxy already running")
        proxy_port = port or settings.proxy_port
        server_url = f"http://127.0.0.1:{settings.port}"
        self.process = subprocess.Popen(
            ["mitmdump", "--listen-port", str(proxy_port), "-s", self.addon_path,
             "--set", f"server_url={server_url}", "--set", f"capture_session_id={session_id}",
             "--set", "connection_strategy=lazy"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return proxy_port

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


proxy_manager = ProxyManager()
