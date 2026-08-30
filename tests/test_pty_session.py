import asyncio
import pytest
from hostinclusion.pty_session import PtySession, PtySessionManager


@pytest.mark.asyncio
async def test_pty_session_lifecycle():
    session = PtySession(command=["/bin/sh"], rows=24, cols=80)
    session.start()
    assert session.is_alive()

    # Write a command to the PTY
    session.write("echo HOST_INCLUSION_PTY_OK\n")

    # Read output
    output = b""
    async for chunk in session.read_stream():
        output += chunk
        if b"HOST_INCLUSION_PTY_OK" in output:
            break

    assert b"HOST_INCLUSION_PTY_OK" in output

    session.resize(30, 100)
    assert session.rows == 30
    assert session.cols == 100

    session.close()
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_pty_session_manager():
    mgr = PtySessionManager()
    session = mgr.create_session(command=["/bin/sh"])
    assert session.id in mgr._sessions

    fetched = mgr.get_session(session.id)
    assert fetched is session

    mgr.close_session(session.id)
    assert mgr.get_session(session.id) is None
