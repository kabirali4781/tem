from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Server:
    country_name: str
    country_code: str
    ip: str
    ssh_key_path: str
    public_key: str = ""
    ssh_user: str = "root"
    ssh_port: int = 22
    wg_interface: str = "awg0"
    wg_conf_path: str = "/etc/amnezia/amneziawg/awg0.conf"
    mtu: int = 1280
    dns: str = "1.1.1.1"
    allowed_ips: str = "0.0.0.0/0"
    jc: int = 4
    jmin: int = 50
    jmax: int = 1000
    s1: int = 0
    s2: int = 0
    h1: int = 1
    h2: int = 2
    h3: int = 3
    h4: int = 4


class ServerStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> list[Server]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Server(**item) for item in data]

    def save(self, servers: Iterable[Server]) -> None:
        payload = [asdict(server) for server in servers]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
