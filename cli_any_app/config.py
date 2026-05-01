from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "cli-any-app"
    debug: bool = False
    host: str = "127.0.0.1"
    allow_lan: bool = False
    port: int = 8000
    proxy_port: int = 8080
    data_dir: Path = Path("data")
    db_url: str = "sqlite+aiosqlite:///data/cli_any_app.db"
    db_create_all: bool = True
    retention_purge_on_startup: bool = False
    mitmproxy_ca_dir: Path = Path.home() / ".mitmproxy"
    anthropic_api_key: str = ""
    admin_password: str = ""
    auth_cookie_name: str = "cli_any_app_session"
    csrf_cookie_name: str = "cli_any_app_csrf"
    session_ttl_seconds: int = 60 * 60 * 12
    ws_token_ttl_seconds: int = 60
    test_auto_auth: bool = False
    raw_body_capture_enabled: bool = False
    max_header_bytes: int = 32_768
    max_body_bytes: int = 131_072
    max_session_capture_bytes: int = 25_000_000
    default_retention_days: int = 30
    llm_model: str = "claude-sonnet-4-6"
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2
    llm_max_tokens: int = 16_384
    llm_temperature: float = 0.0
    generated_smoke_test_enabled: bool = False

    model_config = {"env_prefix": "CLI_ANY_APP_", "env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def bodies_dir(self) -> Path:
        return self.data_dir / "bodies"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"


settings = Settings()
