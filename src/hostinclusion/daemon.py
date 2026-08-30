"""FastAPI daemon service for HostInclusion nodes."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

from hostinclusion.capabilities import NodeInfo, get_node_info
from hostinclusion.discovery import list_tailscale_peers, TailscalePeer
from hostinclusion.pty_session import PtySession, PtySessionManager

manager = PtySessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown events."""
    yield
    # Cleanup all active PTY sessions on server shutdown
    manager.close_all()


app = FastAPI(
    title="HostInclusion Daemon",
    description="Distributed host daemon for remote terminal sessions and resource access over Tailscale",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionRequest(BaseModel):
    command: Optional[List[str]] = None
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    rows: int = 24
    cols: int = 80


class SessionResponse(BaseModel):
    session_id: str
    command: List[str]
    cwd: str
    rows: int
    cols: int
    is_alive: bool


WEB_DIR = Path(__file__).parent / "web"
INDEX_HTML = WEB_DIR / "index.html"


@app.get("/", response_class=FileResponse)
@app.get("/terminal", response_class=FileResponse)
async def serve_terminal_ui():
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return HTMLResponse("<h1>HostInclusion UI not found</h1>", status_code=404)


@app.get("/api/v1/peers", response_model=List[TailscalePeer])
async def get_peers():
    return list_tailscale_peers(probe_port=8765)


@app.get("/health")
@app.get("/api/v1/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/info", response_model=NodeInfo)
async def node_info() -> NodeInfo:
    return get_node_info()


@app.post("/api/v1/terminal/sessions", response_model=SessionResponse)
async def create_terminal_session(req: CreateSessionRequest) -> SessionResponse:
    try:
        session = manager.create_session(
            command=req.command,
            cwd=req.cwd,
            env=req.env,
            rows=req.rows,
            cols=req.cols,
        )
        return SessionResponse(
            session_id=session.id,
            command=session.command,
            cwd=session.cwd,
            rows=session.rows,
            cols=session.cols,
            is_alive=session.is_alive(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create PTY session: {e}")


@app.delete("/api/v1/terminal/sessions/{session_id}")
async def close_terminal_session(session_id: str) -> Dict[str, bool]:
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    manager.close_session(session_id)
    return {"closed": True}


@app.websocket("/api/v1/terminal/ws")
@app.websocket("/api/v1/terminal/ws/{session_id}")
async def terminal_websocket(
    websocket: WebSocket,
    session_id: Optional[str] = None,
    rows: int = Query(default=24),
    cols: int = Query(default=80),
    command: Optional[str] = Query(default=None),
) -> None:
    """Interactive bidirectional WebSocket terminal stream."""
    await websocket.accept()

    session: Optional[PtySession] = None
    if session_id:
        session = manager.get_session(session_id)
        if not session or not session.is_alive():
            await websocket.send_text(json.dumps({"type": "error", "message": "Session not found or terminated"}))
            await websocket.close(code=1008)
            return
    else:
        # Auto-create a new session for this connection
        cmd_list = [command] if command else None
        try:
            session = manager.create_session(command=cmd_list, rows=rows, cols=cols)
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "message": f"Failed to spawn PTY: {e}"}))
            await websocket.close(code=1011)
            return

    async def pty_to_ws() -> None:
        """Stream PTY output bytes to the WebSocket client."""
        try:
            async for chunk in session.read_stream():
                if not chunk:
                    break
                await websocket.send_bytes(chunk)
        except (WebSocketDisconnect, ConnectionResetError):
            pass
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    import asyncio
    pty_task = asyncio.create_task(pty_to_ws())

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                session.write(message["bytes"])
            elif "text" in message and message["text"]:
                text = message["text"]
                # Check for control JSON frame
                if text.startswith("{") and text.endswith("}"):
                    try:
                        control = json.loads(text)
                        msg_type = control.get("type")
                        if msg_type == "resize":
                            r = int(control.get("rows", session.rows))
                            c = int(control.get("cols", session.cols))
                            session.resize(r, c)
                        elif msg_type == "stdin":
                            data = control.get("data", "")
                            session.write(data)
                        elif msg_type == "signal":
                            signum = int(control.get("signum", 15))
                            session.send_signal(signum)
                        continue
                    except (json.JSONDecodeError, ValueError):
                        pass
                # Raw text fallback
                session.write(text)
    except (WebSocketDisconnect, ConnectionResetError):
        pass
    finally:
        pty_task.cancel()
        if not session_id:
            # If the session was ephemeral to this websocket, close it
            session.close()


def start_daemon(host: str = "0.0.0.0", port: int = 8765, log_level: str = "info") -> None:
    """Run the HostInclusion daemon server."""
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    start_daemon()
