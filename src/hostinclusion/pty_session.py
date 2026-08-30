"""Asynchronous PTY session manager for remote terminal execution."""

from __future__ import annotations

import asyncio
import errno
import os
import signal
import sys
import uuid
from typing import AsyncIterator, Dict, List, Optional
import struct
import fcntl
import termios

if sys.platform != "win32":
    import ptyprocess
else:
    ptyprocess = None  # type: ignore


class PtySession:
    """Manages an interactive pseudo-terminal process lifecycle and async I/O."""

    def __init__(
        self,
        command: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        rows: int = 24,
        cols: int = 80,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.command = command or [os.environ.get("SHELL", "/bin/bash")]
        self.cwd = cwd or os.path.expanduser("~")
        self.env = env or dict(os.environ)
        # Ensure TERM is set for rich interactive terminal experiences
        if "TERM" not in self.env:
            self.env["TERM"] = "xterm-256color"
        self.rows = rows
        self.cols = cols

        self._proc: Optional[ptyprocess.PtyProcess] = None
        self._output_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False

    def is_alive(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.isalive()

    def start(self) -> None:
        """Spawn the PTY child process and attach async reader."""
        if sys.platform == "win32":
            raise NotImplementedError("Windows PTY is not yet implemented (requires pywinpty).")

        self._loop = asyncio.get_running_loop()
        self._proc = ptyprocess.PtyProcess.spawn(
            argv=self.command,
            cwd=self.cwd,
            env=self.env,
            dimensions=(self.rows, self.cols),
        )

        # Register non-blocking reader on master file descriptor
        self._loop.add_reader(self._proc.fd, self._on_read_ready)

    def _on_read_ready(self) -> None:
        """Callback when PTY master has data ready to read."""
        if self._proc is None or self._closed:
            return

        try:
            data = os.read(self._proc.fd, 4096)
            if not data:
                # EOF
                self.close()
                return
            self._output_queue.put_nowait(data)
        except OSError as e:
            # On Linux, EIO is raised when the slave end of the PTY closes (normal process exit)
            if e.errno in (errno.EIO, errno.EBADF):
                self.close()
            else:
                self.close()

    async def read_stream(self) -> AsyncIterator[bytes]:
        """Yield output chunks from the PTY process."""
        while not self._closed or not self._output_queue.empty():
            try:
                # Wait for next chunk with a short timeout to check process liveness
                data = await asyncio.wait_for(self._output_queue.get(), timeout=0.1)
                yield data
            except asyncio.TimeoutError:
                if self._closed and self._output_queue.empty():
                    break
                if self._proc and not self._proc.isalive() and self._output_queue.empty():
                    self.close()
                    break

    def write(self, data: bytes | str) -> None:
        """Write input bytes into the PTY stdin."""
        if self._proc is None or not self.is_alive() or self._closed:
            return

        payload = data if isinstance(data, bytes) else data.encode("utf-8")
        try:
            self._proc.write(payload)
            self._proc.flush()
        except OSError:
            self.close()

    def resize(self, rows: int, cols: int) -> None:
        """Resize the PTY terminal window dimensions."""
        self.rows = rows
        self.cols = cols
        if self._proc and self.is_alive():
            try:
                self._proc.setwinsize(rows, cols)
            except Exception:
                pass

    def send_signal(self, sig: int = signal.SIGTERM) -> None:
        """Send a signal to the child process."""
        if self._proc and self.is_alive():
            try:
                os.kill(self._proc.pid, sig)
            except OSError:
                pass

    def close(self) -> None:
        """Clean up and terminate the PTY process."""
        if self._closed:
            return
        self._closed = True

        if self._loop and self._proc:
            try:
                self._loop.remove_reader(self._proc.fd)
            except Exception:
                pass

        if self._proc:
            try:
                if self._proc.isalive():
                    self._proc.terminate(force=True)
            except Exception:
                pass
            try:
                self._proc.close()
            except Exception:
                pass

        # Push sentinel/empty to unblock any waiting consumer
        try:
            self._output_queue.put_nowait(b"")
        except Exception:
            pass


class PtySessionManager:
    """Registry and manager for active PTY sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, PtySession] = {}

    def create_session(
        self,
        command: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        rows: int = 24,
        cols: int = 80,
    ) -> PtySession:
        session = PtySession(command=command, cwd=cwd, env=env, rows=rows, cols=cols)
        session.start()
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Optional[PtySession]:
        session = self._sessions.get(session_id)
        if session and not session.is_alive() and session._closed:
            self._sessions.pop(session_id, None)
            return None
        return session

    def close_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
