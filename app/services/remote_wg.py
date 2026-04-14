from __future__ import annotations

import shlex
import subprocess

from app.services.peer_store import Peer
from app.services.servers_store import Server


class RemoteWG:
    def add_peer(self, server: Server, peer: Peer, keepalive: int) -> None:
        client_ip = peer.address.split("/")[0]
        peer_block = (
            "[Peer]\\n"
            f"PublicKey = {peer.public_key}\\n"
            f"AllowedIPs = {peer.address}\\n"
        )
        append_cmd = (
            "printf '%b' "
            + shlex.quote(peer_block)
            + " | sudo tee -a "
            + shlex.quote(server.wg_conf_path)
            + " >/dev/null"
        )
        awg_cmd = (
            f"sudo awg set {shlex.quote(server.wg_interface)} peer {shlex.quote(peer.public_key)} "
            f"allowed-ips {shlex.quote(peer.address)}"
        )
        route_cmd = (
            f"sudo ip route replace {shlex.quote(client_ip)} dev {shlex.quote(server.wg_interface)}"
        )
        self._ssh(server, f"{append_cmd} && {awg_cmd} && {route_cmd}")

    def remove_peer(self, server: Server, peer: Peer) -> None:
        awg_cmd = f"sudo awg set {shlex.quote(server.wg_interface)} peer {shlex.quote(peer.public_key)} remove"
        cleanup_cmd = self._build_remote_cleanup_cmd(server.wg_conf_path, peer.public_key)
        self._ssh(server, f"{awg_cmd} && {cleanup_cmd}")

    def _build_remote_cleanup_cmd(self, wg_conf_path: str, public_key: str) -> str:
        script = f'''
from pathlib import Path

path = Path({wg_conf_path!r})
target = {public_key!r}
lines = path.read_text(encoding="utf-8").splitlines()
out = []
block = []
in_peer = False
remove_block = False


def flush_block():
    global block, remove_block
    if block and not remove_block:
        out.extend(block)
    block = []
    remove_block = False


for line in lines:
    if line.strip() == "[Peer]":
        if in_peer:
            flush_block()
        in_peer = True
        block = [line]
        remove_block = False
        continue

    if in_peer and line.startswith("[") and line.strip() != "[Peer]":
        flush_block()
        in_peer = False
        out.append(line)
        continue

    if in_peer:
        block.append(line)
        if line.strip() == f"PublicKey = {{target}}":
            remove_block = True
    else:
        out.append(line)

if in_peer:
    flush_block()

path.write_text("\\n".join(out).rstrip() + "\\n", encoding="utf-8")
'''
        return "sudo python3 -c " + shlex.quote(script)

    def _ssh(self, server: Server, remote_cmd: str) -> None:
        cmd = [
            "ssh",
            "-i",
            server.ssh_key_path,
            "-p",
            str(server.ssh_port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=no",
            f"{server.ssh_user}@{server.ip}",
            remote_cmd,
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            msg = completed.stderr.strip() or completed.stdout.strip() or "ssh failed"
            raise RuntimeError(msg)
