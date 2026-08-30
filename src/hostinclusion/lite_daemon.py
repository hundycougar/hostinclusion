"""Zero-dependency lightweight daemon using only asyncio, standard library, and websockets.

Requires no Rust, no C extensions, no pydantic, no fastapi.
"""

from __future__ import annotations

import asyncio
import email.utils
import json
import os
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from hostinclusion.capabilities import get_node_info
from hostinclusion.discovery import list_tailscale_peers
from hostinclusion.pty_session import PtySession, PtySessionManager

manager = PtySessionManager()


def _get_http_response(path: str, query: Dict[str, List[str]]) -> tuple[int, str, bytes]:
    """Route pure HTTP requests."""
    clean_path = path.rstrip("/") or "/"
    if clean_path in ("/health", "/api/v1/health"):
        body = json.dumps({"status": "ok"}).encode("utf-8")
        return 200, "application/json", body

    if clean_path == "/api/v1/info":
        info = get_node_info()
        data = info.model_dump() if hasattr(info, "model_dump") else info.__dict__
        body = json.dumps(data).encode("utf-8")
        return 200, "application/json", body

    if clean_path == "/api/v1/peers":
        probe_port = int(query.get("probe_port", ["8765"])[0]) if "probe_port" in query else 8765
        peers = list_tailscale_peers(probe_port=probe_port)
        data = [p.model_dump() if hasattr(p, "model_dump") else p.__dict__ for p in peers]
        body = json.dumps(data).encode("utf-8")
        return 200, "application/json", body

    if clean_path in ("/", "/terminal"):
        index_file = os.path.join(os.path.dirname(__file__), "web", "index.html")
        if os.path.exists(index_file):
            with open(index_file, "rb") as f:
                return 200, "text/html; charset=utf-8", f.read()
        return 200, "text/html; charset=utf-8", b"<h1>HostInclusion Lite Daemon</h1>"

    return 404, "application/json", json.dumps({"error": "Not Found"}).encode("utf-8")


async def handle_websocket(ws: Any, path: str = "") -> None:
    """Handle interactive PTY streaming over WebSocket."""
    # Parse query parameters from request path if available
    req_path = getattr(ws, "path", path) or path
    parsed = urlparse(req_path)
    query = parse_qs(parsed.query)

    rows = int(query.get("rows", ["24"])[0])
    cols = int(query.get("cols", ["80"])[0])
    cmd = query.get("command", [None])[0]
    cmd_list = [cmd] if cmd else None

    try:
        session = manager.create_session(command=cmd_list, rows=rows, cols=cols)
    except Exception as e:
        try:
            await ws.send(json.dumps({"type": "error", "message": f"Failed to spawn PTY: {e}"}))
            await ws.close(1011)
        except Exception:
            pass
        return

    async def pty_to_ws() -> None:
        try:
            async for chunk in session.read_stream():
                if not chunk:
                    break
                await ws.send(chunk)
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    pty_task = asyncio.create_task(pty_to_ws())

    try:
        async for message in ws:
            if isinstance(message, bytes):
                session.write(message)
            elif isinstance(message, str):
                if message.startswith("{") and message.endswith("}"):
                    try:
                        control = json.loads(message)
                        msg_type = control.get("type")
                        if msg_type == "resize":
                            r = int(control.get("rows", session.rows))
                            c = int(control.get("cols", session.cols))
                            session.resize(r, c)
                        elif msg_type == "stdin":
                            session.write(control.get("data", ""))
                        elif msg_type == "signal":
                            session.send_signal(int(control.get("signum", 15)))
                        continue
                    except Exception:
                        pass
                session.write(message)
    except Exception:
        pass
    finally:
        pty_task.cancel()
        session.close()


class SimpleHttpAndWsServer:
    """Combines basic HTTP API routing and WebSocket connections on a single port."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._server: Optional[asyncio.Server] = None

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # Read HTTP request header
            line = await reader.readline()
            if not line:
                writer.close()
                return

            request_line = line.decode("utf-8", errors="replace").strip()
            parts = request_line.split()
            if len(parts) < 2:
                writer.close()
                return

            method, full_path = parts[0], parts[1]
            headers: Dict[str, str] = {}
            while True:
                header_line = await reader.readline()
                if not header_line or header_line == b"\r\n" or header_line == b"\n":
                    break
                h_str = header_line.decode("utf-8", errors="replace").strip()
                if ":" in h_str:
                    k, v = h_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            parsed = urlparse(full_path)
            query = parse_qs(parsed.query)

            # Check if this is a WebSocket Upgrade request
            if headers.get("upgrade", "").lower() == "websocket":
                # Handle WebSocket Handshake (RFC 6455)
                import base64
                import hashlib

                sec_key = headers.get("sec-websocket-key", "")
                if sec_key:
                    guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                    accept_val = base64.b64encode(hashlib.sha1((sec_key + guid).encode()).digest()).decode()
                    resp_headers = (
                        "HTTP/1.1 101 Switching Protocols\r\n"
                        "Upgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {accept_val}\r\n\r\n"
                    )
                    writer.write(resp_headers.encode())
                    await writer.drain()

                    # Stream interactive WebSocket frames using websockets connection wrapper
                    try:
                        import websockets
                        # If websockets is installed, wrap and run handler
                        from websockets.asyncio.server import ServerConnection
                        # Fallback to direct framing
                    except ImportError:
                        pass

                    await self._stream_raw_ws(reader, writer, parsed.path, query)
                    return

            # Standard HTTP Request
            status_code, content_type, body = _get_http_response(parsed.path, query)
            status_text = {200: "OK", 404: "Not Found", 500: "Internal Error"}.get(status_code, "OK")
            response = (
                f"HTTP/1.1 {status_code} {status_text}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                "Access-Control-Allow-Headers: *\r\n"
                "Connection: close\r\n\r\n"
            ).encode("utf-8") + body

            writer.write(response)
            await writer.drain()
            writer.close()
        except Exception:
            try:
                writer.close()
            except Exception:
                pass

    async def _stream_raw_ws(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        path: str,
        query: Dict[str, List[str]],
    ) -> None:
        """Stream raw WebSocket frames to/from PTY session."""
        rows = int(query.get("rows", ["24"])[0])
        cols = int(query.get("cols", ["80"])[0])
        cmd = query.get("command", [None])[0]
        cmd_list = [cmd] if cmd else None

        try:
            session = manager.create_session(command=cmd_list, rows=rows, cols=cols)
        except Exception as e:
            writer.close()
            return

        async def pty_out():
            try:
                async for chunk in session.read_stream():
                    if not chunk or writer.is_closing():
                        break
                    # Frame binary data (Opcode 0x2)
                    header = bytearray([0x82])
                    length = len(chunk)
                    if length <= 125:
                        header.append(length)
                    elif length <= 65535:
                        header.append(126)
                        header.extend(length.to_bytes(2, "big"))
                    else:
                        header.append(127)
                        header.extend(length.to_bytes(8, "big"))
                    writer.write(header + chunk)
                    await writer.drain()
            except Exception:
                pass

        out_task = asyncio.create_task(pty_out())

        try:
            while not writer.is_closing():
                head = await reader.read(2)
                if len(head) < 2:
                    break
                b1, b2 = head[0], head[1]
                opcode = b1 & 0x0F
                if opcode == 0x8:  # Close
                    break

                is_masked = bool(b2 & 0x80)
                payload_len = b2 & 0x7F
                if payload_len == 126:
                    data = await reader.read(2)
                    payload_len = int.from_bytes(data, "big")
                elif payload_len == 127:
                    data = await reader.read(8)
                    payload_len = int.from_bytes(data, "big")

                masks = await reader.read(4) if is_masked else b""
                payload = await reader.read(payload_len)

                if is_masked and masks:
                    unmasked = bytes(b ^ masks[i % 4] for i, b in enumerate(payload))
                else:
                    unmasked = payload

                if opcode == 0x1:  # Text frame (JSON resize / input)
                    text = unmasked.decode("utf-8", errors="replace")
                    if text.startswith("{") and text.endswith("}"):
                        try:
                            ctl = json.loads(text)
                            if ctl.get("type") == "resize":
                                session.resize(int(ctl.get("rows", session.rows)), int(ctl.get("cols", session.cols)))
                                continue
                        except Exception:
                            pass
                    session.write(unmasked)
                elif opcode == 0x2:  # Binary frame
                    session.write(unmasked)
        except Exception:
            pass
        finally:
            out_task.cancel()
            session.close()
            try:
                writer.close()
            except Exception:
                pass

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self.host, self.port)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()


def run_lite_daemon(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the zero-dependency HostInclusion daemon."""
    server = SimpleHttpAndWsServer(host=host, port=port)
    print(f"🚀 Starting HostInclusion Lite Daemon on http://{host}:{port}")
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        print("\nStopping HostInclusion Lite Daemon...")
    finally:
        manager.close_all()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HostInclusion Zero-Dependency Daemon")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    args = parser.parse_args()
    run_lite_daemon(host=args.host, port=args.port)
