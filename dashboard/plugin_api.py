"""HostInclusion dashboard plugin API for Hermes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

# Ensure hostinclusion is importable
HOSTINCLUSION_SRC = str(Path("/home/ubuntu/dev/hostinclusion/src").resolve())
if HOSTINCLUSION_SRC not in sys.path:
    sys.path.insert(0, HOSTINCLUSION_SRC)

try:
    from hostinclusion.capabilities import get_node_info
    from hostinclusion.discovery import list_tailscale_peers
except ImportError:
    get_node_info = None  # type: ignore
    list_tailscale_peers = None  # type: ignore

router = APIRouter()


@router.get("/peers")
async def get_peers() -> List[Dict[str, Any]]:
    """Discover Tailscale peers and their HostInclusion daemon status."""
    if list_tailscale_peers is None:
        return []
    peers = list_tailscale_peers(probe_port=8765)
    return [p.model_dump() for p in peers]


@router.get("/local-info")
async def get_local_info() -> Dict[str, Any]:
    """Get local machine capabilities and GPU info."""
    if get_node_info is None:
        return {}
    info = get_node_info()
    return info.model_dump()
