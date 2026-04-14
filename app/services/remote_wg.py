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
        awk_cmd = (
            "awk -v k='PublicKey = "
            + peer.public_key
            + "' '"
            + "BEGIN{skip=0} "
            + "\\$0 ~ k {skip=1} "
            + "skip && /^\\[/ {if ($0 ~ /^\\[Peer\\]/) skip=0} "
            + "!skip {print}"
            + "' "
            + shlex.quote(server.wg_conf_path)
            + " > /tmp/awg0.conf && sudo mv /tmp/awg0.conf "
            + shlex.quote(server.wg_conf_path)
        )
        self._ssh(server, f"{awg_cmd} && {awk_cmd}")

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
