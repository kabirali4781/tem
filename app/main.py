from __future__ import annotations

import ipaddress
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Allow direct execution via `python app\main.py` by adding the project root
# to the import path before package imports resolve.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.services.keygen import generate_wireguard_keypair
from app.services.peer_store import Peer, PeerStore, RotationState, RotationStore
from app.services.remote_wg import RemoteWG
from app.services.servers_store import Server, ServerStore

settings = get_settings()
peer_store = PeerStore(settings.peers_store_path)
server_store = ServerStore(settings.servers_store_path)
rotation_store = RotationStore("rotation.json")
remote_wg = RemoteWG()


class StartRequest(BaseModel):
    country_code: str = Field(min_length=2, max_length=8)
    install_id: str | None = Field(default=None, max_length=128)


class StartResponse(BaseModel):
    client_conf: str
    public_key: str
    peer_id: str


class PingRequest(BaseModel):
    peer_id: str


class DisconnectRequest(BaseModel):
    public_key: str = Field(min_length=32, max_length=128)


class DisconnectResponse(BaseModel):
    status: str
    peer_id: str
    public_key: str
    released_ip: str


app = FastAPI(title=settings.app_name)


@app.post(f"{settings.api_prefix}/session/start", response_model=StartResponse)
def start_session(payload: StartRequest) -> StartResponse:
    peers = peer_store.load()
    servers = server_store.load()
    rotations = rotation_store.load()
    now = datetime.utcnow()

    server = _select_server_round_robin(servers, rotations, payload.country_code)
    peer = _create_peer(peers, server, now)
    peers.append(peer)
    _persist(peers, servers, rotations)

    try:
        remote_wg.add_peer(server, peer, settings.wg_persistent_keepalive)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    client_conf = _build_client_conf(peer, server)
    return StartResponse(client_conf=client_conf, public_key=peer.public_key, peer_id=peer.peer_id)


@app.post(f"{settings.api_prefix}/session/disconnect", response_model=DisconnectResponse)
def disconnect_session(payload: DisconnectRequest) -> DisconnectResponse:
    peers = peer_store.load()
    servers = server_store.load()
    rotations = rotation_store.load()

    peer = _find_active_peer_by_public_key(peers, payload.public_key)
    if peer is None:
        raise HTTPException(status_code=404, detail="active peer not found for public key")

    server = _find_server_by_code(servers, peer.server_code)
    if server is None:
        raise HTTPException(status_code=404, detail="server not found for peer")

    try:
        remote_wg.remove_peer(server, peer)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    peer.status = "deleted"
    peer.last_handshake = datetime.utcnow().isoformat() + "Z"
    _persist(peers, servers, rotations)
    return DisconnectResponse(
        status="deleted",
        peer_id=peer.peer_id,
        public_key=peer.public_key,
        released_ip=peer.address,
    )


@app.post(f"{settings.api_prefix}/session/ping")
def ping_session(payload: PingRequest) -> dict[str, str]:
    peers = peer_store.load()
    servers = server_store.load()
    rotations = rotation_store.load()
    now = datetime.utcnow()

    for peer in peers:
        if peer.peer_id == payload.peer_id and peer.status == "active":
            peer.last_handshake = now.isoformat() + "Z"
            _persist(peers, servers, rotations)
            return {"status": "ok"}

    raise HTTPException(status_code=404, detail="peer not found")


def _select_server_round_robin(
    servers: list[Server], rotations: list[RotationState], country_code: str
) -> Server:
    if not servers:
        raise HTTPException(status_code=500, detail="servers.json is empty")

    needle = country_code.strip().lower()
    matching = [s for s in servers if s.country_code.lower().startswith(needle)]
    if not matching:
        raise HTTPException(status_code=404, detail="no server for country code")

    matching.sort(key=lambda s: s.country_code)
    state = _get_rotation_state(rotations, needle)
    idx = state.next_index % len(matching)
    selected = matching[idx]
    state.next_index = (idx + 1) % len(matching)
    return selected


def _get_rotation_state(rotations: list[RotationState], code: str) -> RotationState:
    for state in rotations:
        if state.country_code == code:
            return state
    state = RotationState(country_code=code, next_index=0)
    rotations.append(state)
    return state


def _create_peer(peers: list[Peer], server: Server, now: datetime) -> Peer:
    active_peers = [p for p in peers if p.status == "active"]
    pool_capacity = _pool_peer_capacity()
    max_active_peers = (
        min(settings.max_peers, pool_capacity) if settings.max_peers is not None else pool_capacity
    )
    if len(active_peers) >= max_active_peers:
        deleted = [p for p in peers if p.status == "deleted"]
        if deleted:
            reuse = deleted[0]
            reuse.status = "active"
            reuse.last_handshake = now.isoformat() + "Z"
            reuse.server_code = server.country_code
            return reuse
        oldest = min(active_peers, key=lambda p: p.created_at)
        oldest.status = "deleted"

    private_key, public_key = generate_wireguard_keypair()
    address = _allocate_address(peers)
    return Peer(
        peer_id=str(uuid4()),
        public_key=public_key,
        private_key=private_key,
        address=address,
        last_handshake=now.isoformat() + "Z",
        created_at=now.isoformat() + "Z",
        status="active",
        server_code=server.country_code,
    )


def _allocate_address(peers: list[Peer]) -> str:
    network = ipaddress.ip_network(settings.address_pool_cidr, strict=False)
    if network.version != 4:
        raise HTTPException(status_code=400, detail="ADDRESS_POOL_CIDR must be IPv4")

    used = {
        ipaddress.ip_address(peer.address.split("/")[0])
        for peer in peers
        if peer.status == "active"
    }
    for host in _iter_allocatable_hosts(network):
        if host in used:
            continue
        return f"{host}/32"
    raise HTTPException(status_code=409, detail="address pool exhausted")


def _iter_allocatable_hosts(network: ipaddress.IPv4Network):
    for host in network:
        last_octet = int(str(host).split(".")[-1])
        if 2 <= last_octet <= 253:
            yield host


def _pool_peer_capacity() -> int:
    network = ipaddress.ip_network(settings.address_pool_cidr, strict=False)
    if network.version != 4:
        raise HTTPException(status_code=400, detail="ADDRESS_POOL_CIDR must be IPv4")
    return sum(1 for _ in _iter_allocatable_hosts(network))


def _build_client_conf(peer: Peer, server: Server) -> str:
    endpoint = server.ip
    if ":" not in endpoint:
        endpoint = f"{endpoint}:{settings.wg_default_port}"
    return "\n".join(
        [
            "[Interface]",
            "# The Client's Private Key",
            f"PrivateKey = {peer.private_key}",
            f"Address = {peer.address}",
            "# Critical for mobile networks",
            f"MTU = {server.mtu}",
            f"DNS = {server.dns}",
            "",
            "",
            "# AmneziaWG Parameters (Must match Server)",
            f"Jc = {server.jc}",
            f"Jmin = {server.jmin}",
            f"Jmax = {server.jmax}",
            f"S1 = {server.s1}",
            f"S2 = {server.s2}",
            f"H1 = {server.h1}",
            f"H2 = {server.h2}",
            f"H3 = {server.h3}",
            f"H4 = {server.h4}",
            "",
            "[Peer]",
            "# The Server's Public Key",
            f"PublicKey = {server.public_key}",
            f"Endpoint = {endpoint}",
            f"AllowedIPs = {server.allowed_ips}",
            f"PersistentKeepalive = {settings.wg_persistent_keepalive}",
            "",
        ]
    )


def _find_active_peer_by_public_key(peers: list[Peer], public_key: str) -> Peer | None:
    for peer in peers:
        if peer.public_key == public_key and peer.status == "active":
            return peer
    return None


def _find_server_by_code(servers: list[Server], server_code: str) -> Server | None:
    for server in servers:
        if server.country_code == server_code:
            return server
    return None


def _persist(peers: list[Peer], servers: list[Server], rotations: list[RotationState]) -> None:
    peer_store.save(peers)
    server_store.save(servers)
    rotation_store.save(rotations)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
