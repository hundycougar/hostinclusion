"""HostInclusion dashboard plugin API for Hermes with WebSocket proxying."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import websockets

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


@router.websocket("/ws")
async def terminal_proxy_ws(
    client_ws: WebSocket,
    host: str = Query(default="localhost"),
    port: int = Query(default=8765),
    rows: int = Query(default=24),
    cols: int = Query(default=80),
    command: Optional[str] = Query(default=None),
) -> None:
    """Proxy WebSocket connection from web browser dashboard through Hermes VPS to target Tailscale host."""
    await client_ws.accept()

    query = f"?rows={rows}&cols={cols}"
    if command:
        query += f"&command={command}"
    target_url = f"ws://{host}:{port}/api/v1/terminal/ws{query}"

    try:
        async with websockets.connect(target_url, ping_interval=20, ping_timeout=20) as target_ws:
            async def client_to_target() -> None:
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"]:
                            await target_ws.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            await target_ws.send(msg["text"])
                except Exception:
                    pass

            async def target_to_client() -> None:
                try:
                    async for message in target_ws:
                        if isinstance(message, bytes):
                            await client_ws.send_bytes(message)
                        else:
                            await client_ws.send_text(message)
                except Exception:
                    pass

            task_in = asyncio.create_task(client_to_target())
            task_out = asyncio.create_task(target_to_client())

            done, pending = await asyncio.wait(
                [task_in, task_out],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
    except Exception as e:
        try:
            await client_ws.send_text(json.dumps({"type": "error", "message": f"Connection failed to host {host}:{port}: {e}"}))
            await client_ws.close(code=1011)
        except Exception:
            pass
