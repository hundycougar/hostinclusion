"""Interactive terminal client for HostInclusion WebSocket sessions."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from typing import Optional
import websockets

if sys.platform != "win32":
    import termios
    import tty


def get_terminal_size() -> tuple[int, int]:
    """Return (rows, cols)."""
    try:
        cols, rows = os.get_terminal_size()
        return rows, cols
    except Exception:
        return 24, 80


class TerminalClient:
    """Manages an interactive raw TTY connection to a HostInclusion daemon."""

    def __init__(self, host: str, port: int = 8765, command: Optional[str] = None) -> None:
        self.host = host
        self.port = port
        self.command = command
        self._ws_url = f"ws://{host}:{port}/api/v1/terminal/ws"
        self._orig_termios = None

    async def connect_and_stream(self) -> None:
        """Attach local TTY to remote WebSocket session."""
        rows, cols = get_terminal_size()
        query_params = f"?rows={rows}&cols={cols}"
        if self.command:
            query_params += f"&command={self.command}"

        url = f"{self._ws_url}{query_params}"

        if not sys.stdin.isatty():
            raise RuntimeError("Terminal client must be run in an interactive TTY.")

        # Save existing termios settings
        fd = sys.stdin.fileno()
        self._orig_termios = termios.tcgetattr(fd)

        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                # Put stdin into raw mode
                tty.setraw(fd)

                loop = asyncio.get_running_loop()

                # Handle terminal window resize (SIGWINCH)
                def handle_resize():
                    new_rows, new_cols = get_terminal_size()
                    resize_msg = json.dumps({"type": "resize", "rows": new_rows, "cols": new_cols})
                    asyncio.create_task(ws.send(resize_msg))

                if hasattr(signal, "SIGWINCH"):
                    loop.add_signal_handler(signal.SIGWINCH, handle_resize)

                stdin_queue: asyncio.Queue[bytes] = asyncio.Queue()

                def on_stdin_ready():
                    try:
                        chunk = os.read(fd, 1024)
                        if chunk:
                            stdin_queue.put_nowait(chunk)
                    except OSError:
                        pass

                loop.add_reader(fd, on_stdin_ready)

                async def ws_to_stdout():
                    try:
                        async for message in ws:
                            if isinstance(message, bytes):
                                sys.stdout.buffer.write(message)
                                sys.stdout.buffer.flush()
                            elif isinstance(message, str):
                                sys.stdout.write(message)
                                sys.stdout.flush()
                    except (websockets.ConnectionClosed, asyncio.CancelledError):
                        pass

                async def stdin_to_ws():
                    try:
                        while True:
                            chunk = await stdin_queue.get()
                            await ws.send(chunk)
                    except (websockets.ConnectionClosed, asyncio.CancelledError):
                        pass

                stdout_task = asyncio.create_task(ws_to_stdout())
                stdin_task = asyncio.create_task(stdin_to_ws())

                done, pending = await asyncio.wait(
                    [stdout_task, stdin_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

        finally:
            # Clean up readers and signal handlers
            try:
                loop = asyncio.get_running_loop()
                loop.remove_reader(fd)
                if hasattr(signal, "SIGWINCH"):
                    loop.remove_signal_handler(signal.SIGWINCH)
            except Exception:
                pass

            # Restore original terminal settings
            if self._orig_termios:
                termios.tcsetattr(fd, termios.TCSADRAIN, self._orig_termios)


def run_interactive_session(host: str, port: int = 8765, command: Optional[str] = None) -> None:
    """Run an interactive terminal session over WebSocket."""
    client = TerminalClient(host=host, port=port, command=command)
    asyncio.run(client.connect_and_stream())
