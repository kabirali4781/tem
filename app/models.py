from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class VPNServer(Base):
    __tablename__ = "vpn_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), index=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key: Mapped[str] = mapped_column(String(80), nullable=False)
    listen_port: Mapped[int] = mapped_column(Integer, default=51820, nullable=False)
    interface_name: Mapped[str] = mapped_column(String(32), nullable=False)
    address_pool_cidr: Mapped[str] = mapped_column(String(32), nullable=False)
    max_sessions: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sessions: Mapped[list[Session]] = relationship(back_populates="server")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    install_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    country_preference: Mapped[str | None] = mapped_column(String(2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    server_id: Mapped[int] = mapped_column(ForeignKey("vpn_servers.id"), nullable=False)
    client_private_key: Mapped[str] = mapped_column(String(80), nullable=False)
    client_public_key: Mapped[str] = mapped_column(String(80), nullable=False)
    client_address: Mapped[str] = mapped_column(String(64), nullable=False)
    config_token: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    config_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    config_served_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    server: Mapped[VPNServer] = relationship(back_populates="sessions")
