from io import BytesIO
import json
from unittest.mock import MagicMock, patch
from hostinclusion.discovery import list_tailscale_peers, TailscalePeer


def test_list_tailscale_peers_mock():
    mock_status = {
        "Self": {
            "HostName": "my-desktop",
            "DNSName": "my-desktop.tailnet.ts.net.",
            "TailscaleIPs": ["100.64.0.1"],
            "OS": "linux",
            "Online": True,
        },
        "Peer": {
            "node2": {
                "HostName": "gpu-rig-4070",
                "DNSName": "gpu-rig-4070.tailnet.ts.net.",
                "TailscaleIPs": ["100.64.0.2"],
                "OS": "linux",
                "Online": True,
            }
        },
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "hostname": "gpu-rig-4070",
        "capabilities": ["terminal", "gpu_cuda"],
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("hostinclusion.discovery.get_tailscale_status", return_value=mock_status):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            peers = list_tailscale_peers(probe_port=8765)
            assert len(peers) == 2

            self_peer = [p for p in peers if p.is_self][0]
            assert self_peer.hostname == "my-desktop"
            assert self_peer.tailscale_ips == ["100.64.0.1"]

            remote_peer = [p for p in peers if not p.is_self][0]
            assert remote_peer.hostname == "gpu-rig-4070"
            assert remote_peer.hostinclusion_active is True
            assert remote_peer.node_info is not None
            assert "gpu_cuda" in remote_peer.node_info["capabilities"]
