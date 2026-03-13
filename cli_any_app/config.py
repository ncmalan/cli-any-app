from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "cli-any-app"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    proxy_port: int = 8080
    data_dir: Path = Path("data")
    db_url: str = "sqlite+aiosqlite:///data/cli_any_app.db"
    mitmproxy_ca_dir: Path = Path.home() / ".mitmproxy"
    anthropic_api_key: str = ""

    model_config = {"env_prefix": "CLI_ANY_APP_", "env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def bodies_dir(self) -> Path:
        return self.data_dir / "bodies"


settings = Settings()
