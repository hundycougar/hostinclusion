import platform
import socket
from unittest.mock import patch
from hostinclusion.capabilities import detect_gpus, get_node_info, NodeInfo, GPUInfo


def test_get_node_info_basic():
    info = get_node_info()
    assert isinstance(info, NodeInfo)
    assert info.hostname == socket.gethostname()
    assert info.platform == platform.system()
    assert "terminal" in info.capabilities


def test_detect_gpus_mocked_success():
    fake_output = "NVIDIA GeForce RTX 4070, 12288, 11000, 550.54.14\n"
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = fake_output
            gpus = detect_gpus()
            assert len(gpus) == 1
            assert gpus[0].name == "NVIDIA GeForce RTX 4070"
            assert gpus[0].memory_total_mb == 12288
            assert gpus[0].memory_free_mb == 11000
            assert gpus[0].driver_version == "550.54.14"


def test_detect_gpus_none_when_no_tool():
    with patch("shutil.which", return_value=None):
        gpus = detect_gpus()
        assert gpus == []
