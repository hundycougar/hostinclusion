"""Tailscale network discovery and peer management for HostInclusion."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional
import httpx

try:
    from pydantic import BaseModel, Field  # type: ignore
except Exception:
    class BaseModel:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> Dict[str, Any]:
            res: Dict[str, Any] = {}
            for k, v in self.__dict__.items():
                if isinstance(v, list):
                    res[k] = [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
                elif hasattr(v, "model_dump"):
                    res[k] = v.model_dump()
                else:
                    res[k] = v
            return res

        def dict(self) -> Dict[str, Any]:
            return self.model_dump()

    def Field(default: Any = None, default_factory: Any = None) -> Any:  # type: ignore
        if default_factory is not None:
            return default_factory()
        return default


class TailscalePeer(BaseModel):
    hostname: str
    dns_name: str
    tailscale_ips: List[str] = Field(default_factory=list)
    os: str = "unknown"
    online: bool = False
    is_self: bool = False
    hostinclusion_active: bool = False
    node_info: Optional[Dict[str, Any]] = None


def get_tailscale_status() -> Dict[str, Any]:
    """Retrieve raw Tailscale status as JSON."""
    tailscale_bin = shutil.which("tailscale")
    if not tailscale_bin:
        return {}

    try:
        res = subprocess.run(
            [tailscale_bin, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return {}


def list_tailscale_peers(probe_port: Optional[int] = 8765) -> List[TailscalePeer]:
    """List all peers on the current Tailscale network with optional HostInclusion probe."""
    raw = get_tailscale_status()
    peers: List[TailscalePeer] = []

    if not raw:
        return peers

    self_node = raw.get("Self", {})
    if self_node:
        self_ips = self_node.get("TailscaleIPs", [])
        self_peer = TailscalePeer(
            hostname=self_node.get("HostName", "localhost"),
            dns_name=self_node.get("DNSName", "").rstrip("."),
            tailscale_ips=self_ips,
            os=self_node.get("OS", "unknown"),
            online=self_node.get("Online", True),
            is_self=True,
        )
        peers.append(self_peer)

    peer_map = raw.get("Peer", {})
    for _, peer_data in peer_map.items():
        dns_name = peer_data.get("DNSName", "").rstrip(".")
        ips = peer_data.get("TailscaleIPs", [])
        p = TailscalePeer(
            hostname=peer_data.get("HostName", dns_name or "unknown"),
            dns_name=dns_name,
            tailscale_ips=ips,
            os=peer_data.get("OS", "unknown"),
            online=peer_data.get("Online", False),
            is_self=False,
        )
        peers.append(p)

    if probe_port:
        for peer in peers:
            target_ip = peer.tailscale_ips[0] if peer.tailscale_ips else peer.dns_name
            if not target_ip:
                continue
            url = f"http://{target_ip}:{probe_port}/api/v1/info"
            try:
                resp = httpx.get(url, timeout=0.8)
                if resp.status_code == 200:
                    peer.hostinclusion_active = True
                    peer.node_info = resp.json()
            except Exception:
                peer.hostinclusion_active = False

    return peers
