from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.services.peer_store import Peer


def load_base_conf(path: str) -> str:
    base_path = Path(path)
    if base_path.exists():
        return base_path.read_text(encoding="utf-8").strip() + "\n\n"
    # Minimal fallback if base file is missing.
    return "[Interface]\nPrivateKey = REPLACE_WITH_SERVER_PRIVATE_KEY\nAddress = 10.10.1.1/22\n\n"


def render_peer_block(peer: Peer) -> str:
    return (
        "[Peer]\n"
        f"PublicKey = {peer.public_key}\n"
        f"AllowedIPs = {peer.address}\n\n"
    )


def write_wg_conf(base_conf_path: str, out_conf_path: str, peers: Iterable[Peer]) -> None:
    base = load_base_conf(base_conf_path)
    blocks = "".join(render_peer_block(peer) for peer in peers if peer.status == "active")
    Path(out_conf_path).write_text(base + blocks, encoding="utf-8")
