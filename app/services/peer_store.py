from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class Peer:
    peer_id: str
    public_key: str
    private_key: str
    address: str
    last_handshake: str
    created_at: str
    status: str = "active"
    server_code: str = ""


@dataclass
class RotationState:
    country_code: str
    next_index: int = 0


class PeerStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> list[Peer]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Peer(**item) for item in data]

    def save(self, peers: Iterable[Peer]) -> None:
        payload = [asdict(peer) for peer in peers]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def now_iso() -> str:
        return datetime.utcnow().isoformat() + "Z"


class RotationStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> list[RotationState]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [RotationState(**item) for item in data]

    def save(self, states: Iterable[RotationState]) -> None:
        payload = [asdict(state) for state in states]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
