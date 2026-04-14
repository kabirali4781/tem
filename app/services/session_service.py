from __future__ import annotations

import ipaddress
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Session as SessionModel
from app.models import VPNServer
from app.schemas import ServerItem
from app.services.keygen import generate_wireguard_keypair
from app.services.server_selector import select_best_server
from app.services.wireguard_agent import WireGuardAgent


class SessionService:
    def __init__(self, settings: Settings, wg_agent: WireGuardAgent) -> None:
        self.settings = settings
        self.wg_agent = wg_agent

    def start_session(self, db: Session, install_id: str, country_preference: str | None) -> SessionModel:
        now = datetime.utcnow()
        existing = db.scalars(
            select(SessionModel).where(
                and_(SessionModel.install_id == install_id, SessionModel.status == "active")
            )
        ).all()
        for s in existing:
            self._terminate_session(db=db, session=s, reason="replaced_by_new_session", at=now)

        server = select_best_server(db, country_preference)
        client_private_key, client_public_key = generate_wireguard_keypair()
        client_address = self._allocate_client_address(db, server.id, server.address_pool_cidr)

        session = SessionModel(
            id=str(uuid4()),
            install_id=install_id,
            country_preference=country_preference.upper() if country_preference else None,
            status="active",
            server_id=server.id,
            client_private_key=client_private_key,
            client_public_key=client_public_key,
            client_address=client_address,
            config_token=str(uuid4()),
            config_token_expires_at=now + timedelta(seconds=self.settings.config_token_ttl_seconds),
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.session_ttl_seconds),
            last_seen_at=now,
        )
        db.add(session)

        self.wg_agent.add_peer(
            server=server,
            client_public_key=client_public_key,
            client_address=client_address,
            persistent_keepalive=self.settings.wg_persistent_keepalive,
        )
        db.commit()
        db.refresh(session)
        return session

    def get_config_once(self, db: Session, config_token: str) -> tuple[SessionModel, str]:
        now = datetime.utcnow()
        session = db.scalar(
            select(SessionModel).where(
                and_(SessionModel.config_token == config_token, SessionModel.status == "active")
            )
        )
        if not session:
            raise ValueError("Invalid config token")
        if not session.config_token_expires_at or session.config_token_expires_at < now:
            raise ValueError("Config token expired")

        server = db.get(VPNServer, session.server_id)
        if not server:
            raise ValueError("Server not found for session")

        conf = self._build_client_conf(session, server)
        session.config_served_at = now
        session.config_token = None
        session.config_token_expires_at = None
        db.commit()
        return session, conf

    def ping_session(self, db: Session, session_id: str) -> SessionModel:
        session = self._get_active_session(db, session_id)
        now = datetime.utcnow()
        if session.expires_at < now:
            self._terminate_session(db=db, session=session, reason="expired", at=now)
            db.commit()
            raise ValueError("Session expired")
        session.last_seen_at = now
        db.commit()
        db.refresh(session)
        return session

    def renew_session(self, db: Session, session_id: str) -> SessionModel:
        session = self._get_active_session(db, session_id)
        now = datetime.utcnow()
        session.expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
        session.last_seen_at = now
        db.commit()
        db.refresh(session)
        return session

    def end_session(self, db: Session, session_id: str, reason: str | None) -> SessionModel:
        session = self._get_active_session(db, session_id)
        self._terminate_session(db=db, session=session, reason=reason or "client_request", at=datetime.utcnow())
        db.commit()
        db.refresh(session)
        return session

    def cleanup_expired_sessions(self, db: Session) -> int:
        now = datetime.utcnow()
        heartbeat_cutoff = now - timedelta(seconds=self.settings.heartbeat_timeout_seconds)
        to_stop = db.scalars(
            select(SessionModel).where(
                and_(
                    SessionModel.status == "active",
                    ((SessionModel.expires_at < now) | (SessionModel.last_seen_at < heartbeat_cutoff)),
                )
            )
        ).all()
        for session in to_stop:
            reason = "expired" if session.expires_at < now else "heartbeat_timeout"
            self._terminate_session(db=db, session=session, reason=reason, at=now)
        if to_stop:
            db.commit()
        return len(to_stop)

    def list_servers(self, db: Session) -> list[ServerItem]:
        rows = db.execute(
            select(
                VPNServer,
                func.count(SessionModel.id).filter(SessionModel.status == "active").label("active_count"),
            )
            .outerjoin(SessionModel, SessionModel.server_id == VPNServer.id)
            .group_by(VPNServer.id)
            .order_by(VPNServer.country_code.asc(), VPNServer.name.asc())
        ).all()
        return [
            ServerItem(
                id=server.id,
                name=server.name,
                country_code=server.country_code,
                endpoint=server.endpoint,
                active_sessions=active_count,
                max_sessions=server.max_sessions,
                utilization=round(active_count / max(server.max_sessions, 1), 4),
            )
            for server, active_count in rows
        ]

    def seed_servers(self, db: Session) -> None:
        existing_count = db.scalar(select(func.count(VPNServer.id)))
        if existing_count and existing_count > 0:
            return
        for seed in self.settings.load_seed_servers():
            db.add(
                VPNServer(
                    name=seed.name,
                    country_code=seed.country_code.upper(),
                    endpoint=seed.endpoint,
                    public_key=seed.public_key,
                    listen_port=seed.listen_port,
                    interface_name=seed.interface_name,
                    address_pool_cidr=seed.address_pool_cidr,
                    max_sessions=seed.max_sessions,
                    is_active=seed.is_active,
                )
            )
        db.commit()

    def _allocate_client_address(self, db: Session, server_id: int, pool_cidr: str) -> str:
        network = ipaddress.ip_network(pool_cidr)
        used_ips = {
            ipaddress.ip_address(ip.split("/")[0])
            for ip in db.scalars(
                select(SessionModel.client_address).where(
                    and_(SessionModel.server_id == server_id, SessionModel.status == "active")
                )
            ).all()
        }

        for host in network.hosts():
            # Keep .1 available for gateway/use by server itself.
            if int(host) == int(network.network_address) + 1:
                continue
            if host in used_ips:
                continue
            return f"{host}/32"
        raise ValueError(f"Address pool exhausted for server {server_id}")

    def _build_client_conf(self, session: SessionModel, server: VPNServer) -> str:
        lines = [
            "[Interface]",
            f"PrivateKey = {session.client_private_key}",
            f"Address = {session.client_address}",
            f"DNS = {self.settings.wg_dns}",
            "",
            "[Peer]",
            f"PublicKey = {server.public_key}",
            f"AllowedIPs = {self.settings.wg_allowed_ips}",
            f"Endpoint = {server.endpoint}:{server.listen_port}",
            f"PersistentKeepalive = {self.settings.wg_persistent_keepalive}",
            "",
        ]
        return "\n".join(lines)

    def _get_active_session(self, db: Session, session_id: str) -> SessionModel:
        session = db.get(SessionModel, session_id)
        if not session or session.status != "active":
            raise ValueError("Session not active or not found")
        return session

    def _terminate_session(self, db: Session, session: SessionModel, reason: str, at: datetime) -> None:
        server = db.get(VPNServer, session.server_id)
        if server:
            self.wg_agent.remove_peer(server=server, client_public_key=session.client_public_key)
        session.status = "ended"
        session.ended_at = at
        session.end_reason = reason
        session.config_token = None
        session.config_token_expires_at = None

    @staticmethod
    def generate_download_token() -> str:
        return secrets.token_urlsafe(24)
