from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    install_id: str = Field(min_length=8, max_length=128)
    country_preference: str | None = Field(default=None, min_length=2, max_length=2)


class StartSessionResponse(BaseModel):
    session_id: str
    config_token: str
    config_token_expires_at: datetime
    session_expires_at: datetime
    server_name: str
    country_code: str


class ConfigResponse(BaseModel):
    session_id: str
    client_conf: str


class SessionPingRequest(BaseModel):
    session_id: str


class SessionPingResponse(BaseModel):
    status: str
    expires_at: datetime
    last_seen_at: datetime


class SessionEndRequest(BaseModel):
    session_id: str
    reason: str | None = None


class SessionRenewRequest(BaseModel):
    session_id: str
    ad_event_id: str | None = None


class GenericSessionResponse(BaseModel):
    session_id: str
    status: str
    expires_at: datetime


class ServerItem(BaseModel):
    id: int
    name: str
    country_code: str
    endpoint: str
    utilization: float
    active_sessions: int
    max_sessions: int


class ServerListResponse(BaseModel):
    servers: list[ServerItem]
