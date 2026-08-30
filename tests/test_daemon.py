import json
import pytest
from fastapi.testclient import TestClient
from hostinclusion.daemon import app


client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_node_info_endpoint():
    resp = client.get("/api/v1/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "hostname" in data
    assert "capabilities" in data
    assert "terminal" in data["capabilities"]


def test_create_and_delete_session():
    resp = client.post("/api/v1/terminal/sessions", json={"command": ["/bin/sh"], "rows": 24, "cols": 80})
    assert resp.status_code == 200
    session_data = resp.json()
    session_id = session_data["session_id"]
    assert session_data["is_alive"] is True

    # Delete session
    del_resp = client.delete(f"/api/v1/terminal/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"closed": True}


def test_serve_ui():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "HostInclusion" in resp.text
    assert "xterm" in resp.text


def test_api_peers_endpoint():
    resp = client.get("/api/v1/peers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_websocket_terminal_stream():
    with client.websocket_connect("/api/v1/terminal/ws?command=/bin/sh") as ws:
        # Send command
        ws.send_bytes(b"echo TEST_WS_STREAM\n")

        # Read responses until keyword seen
        received = b""
        for _ in range(20):
            try:
                data = ws.receive_bytes()
                received += data
                if b"TEST_WS_STREAM" in received:
                    break
            except Exception:
                break

        assert b"TEST_WS_STREAM" in received

        # Test resize control message
        ws.send_text(json.dumps({"type": "resize", "rows": 35, "cols": 120}))
