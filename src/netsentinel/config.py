"""Runtime configuration.

All settings are read from environment variables (optionally via a ``.env`` file).
The same module is imported by both the hub and the sensor; each side only uses
the fields relevant to it. See ``.env.example`` for a documented template.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NETSENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ shared
    role: str = Field(default="hub", description="hub | sensor")
    data_dir: Path = Field(default=Path("./var"), description="Writable state directory.")
    log_level: str = Field(default="INFO")

    # Shared secret used to authenticate sensor -> hub ingest calls and the
    # worker/token protected API routes. Generate with: openssl rand -hex 32
    api_token: str = Field(default="change-me-please", min_length=8)

    # ------------------------------------------------------------------ hub
    hub_host: str = Field(default="0.0.0.0")
    hub_port: int = Field(default=8080)
    # Optional HTTP basic auth for the dashboard (leave blank to disable).
    dashboard_user: str = Field(default="")
    dashboard_password: str = Field(default="")
    # Retention for high-volume tables, in days.
    dns_retention_days: int = Field(default=14)
    event_retention_days: int = Field(default=90)

    # Notification sink. One of: none | log | ntfy | telegram | webhook
    notify_backend: str = Field(default="log")
    ntfy_url: str = Field(default="https://ntfy.sh")
    ntfy_topic: str = Field(default="")
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    webhook_url: str = Field(default="")

    # Threat-intel enrichment for observed external IPs.
    ti_enabled: bool = Field(default=True)
    abuseipdb_api_key: str = Field(default="")
    # Local newline-delimited blocklist of bad domains/IPs, refreshed by cron.
    blocklist_path: Path = Field(default=Path("./data/blocklist.txt"))

    # ------------------------------------------------------------------ sensor
    hub_url: str = Field(default="http://127.0.0.1:8080", description="Where the hub lives.")
    sensor_id: str = Field(default="sensor-1")
    monitor_interface: str = Field(default="eth0")
    # CIDR the sensor is allowed to probe. Discovery/port scans never leave it.
    local_subnet: str = Field(default="192.168.1.0/24")
    discovery_interval_seconds: int = Field(default=300)
    portscan_interval_seconds: int = Field(default=3600)
    dns_flush_interval_seconds: int = Field(default=60)
    # nmap options for the scheduled port-change scan. Kept deliberately light.
    portscan_nmap_args: str = Field(default="-sS -T3 --top-ports 200 -Pn")

    @field_validator("role")
    @classmethod
    def _role_known(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"hub", "sensor"}:
            raise ValueError("role must be 'hub' or 'sensor'")
        return v

    @field_validator("notify_backend")
    @classmethod
    def _notify_known(cls, v: str) -> str:
        v = v.lower().strip()
        allowed = {"none", "log", "ntfy", "telegram", "webhook"}
        if v not in allowed:
            raise ValueError(f"notify_backend must be one of {sorted(allowed)}")
        return v

    @property
    def db_path(self) -> Path:
        return self.data_dir / "netsentinel.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
