from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "WG Simple Control"
    api_prefix: str = "/v1"

    # WireGuard defaults
    wg_allowed_ips: str = "0.0.0.0/0, ::/0"
    wg_dns: str = "1.1.1.1,8.8.8.8"
    wg_persistent_keepalive: int = 25
    wg_default_port: int = 51820

    # Peer control
    address_pool_cidr: str = "10.0.0.1/22"
    max_peers: int | None = None

    # Files
    wg_base_conf_path: str = "awg0.base.conf"
    wg_conf_path: str = "awg0.conf"
    peers_store_path: str = "peers.json"
    servers_store_path: str = "servers.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()