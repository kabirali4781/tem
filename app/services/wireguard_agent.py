from __future__ import annotations

import subprocess
from collections import defaultdict
from datetime import datetime

from app.models import VPNServer


class WireGuardAgent:
    """Applies peer changes to WireGuard nodes.

    By default it runs in dry mode to keep local development simple.
    """

    def __init__(self, enable_real_wg: bool = False) -> None:
        self.enable_real_wg = enable_real_wg
        self._peers: dict[int, set[str]] = defaultdict(set)

    def add_peer(
        self,
        *,
        server: VPNServer,
        client_public_key: str,
        client_address: str,
        persistent_keepalive: int,
    ) -> None:
        self._peers[server.id].add(client_public_key)
        if not self.enable_real_wg:
            return
        cmd = [
            "wg",
            "set",
            server.interface_name,
            "peer",
            client_public_key,
            "allowed-ips",
            client_address,
            "persistent-keepalive",
            str(persistent_keepalive),
        ]
        self._run(cmd)

    def remove_peer(self, *, server: VPNServer, client_public_key: str) -> None:
        self._peers[server.id].discard(client_public_key)
        if not self.enable_real_wg:
            return
        cmd = ["wg", "set", server.interface_name, "peer", client_public_key, "remove"]
        self._run(cmd)

    def _run(self, cmd: list[str]) -> None:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"WireGuard command failed: {' '.join(cmd)} | {completed.stderr.strip()}")

    @property
    def peers_snapshot(self) -> dict[int, int]:
        return {server_id: len(peers) for server_id, peers in self._peers.items()}

    @staticmethod
    def utcnow() -> datetime:
        return datetime.utcnow()
