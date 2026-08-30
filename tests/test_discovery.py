from unittest.mock import patch
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

    with patch("hostinclusion.discovery.get_tailscale_status", return_value=mock_status):
        with patch("httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "hostname": "gpu-rig-4070",
                "capabilities": ["terminal", "gpu_cuda"],
            }

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
