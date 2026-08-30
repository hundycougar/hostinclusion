"""System capabilities and hardware detection for HostInclusion nodes."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field  # type: ignore
except Exception:
    class BaseModel:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> Dict[str, Any]:
            res: Dict[str, Any] = {}
            for k, v in self.__dict__.items():
                if isinstance(v, list):
                    res[k] = [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
                elif hasattr(v, "model_dump"):
                    res[k] = v.model_dump()
                else:
                    res[k] = v
            return res

        def dict(self) -> Dict[str, Any]:
            return self.model_dump()

    def Field(default: Any = None, default_factory: Any = None) -> Any:  # type: ignore
        if default_factory is not None:
            return default_factory()
        return default


class GPUInfo(BaseModel):
    name: str
    memory_total_mb: int | None = None
    memory_free_mb: int | None = None
    driver_version: str | None = None
    cuda_version: str | None = None


class NodeInfo(BaseModel):
    hostname: str
    platform: str
    os_version: str
    architecture: str
    capabilities: List[str] = Field(default_factory=list)
    gpus: List[GPUInfo] = Field(default_factory=list)
    default_shell: str
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)


def detect_gpus() -> List[GPUInfo]:
    """Detect NVIDIA GPUs via nvidia-smi if available."""
    gpus: List[GPUInfo] = []
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return gpus

    try:
        query_cmd = [
            nvidia_smi,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(
            query_cmd,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    name, mem_total, mem_free, driver = parts[:4]
                    gpus.append(
                        GPUInfo(
                            name=name,
                            memory_total_mb=int(mem_total) if mem_total.isdigit() else None,
                            memory_free_mb=int(mem_free) if mem_free.isdigit() else None,
                            driver_version=driver,
                        )
                    )
    except Exception:
        # Fallback cleanly if nvidia-smi fails or times out
        pass

    return gpus


def get_default_shell() -> str:
    """Get the preferred default shell for this host."""
    if platform.system() == "Windows":
        return os.environ.get("COMSPEC", "cmd.exe")
    return os.environ.get("SHELL", "/bin/bash")


def get_node_info() -> NodeInfo:
    """Gather complete node information and active capabilities."""
    gpus = detect_gpus()
    capabilities = ["terminal"]
    if gpus:
        capabilities.append("gpu_cuda")

    return NodeInfo(
        hostname=socket.gethostname(),
        platform=platform.system(),
        os_version=platform.release(),
        architecture=platform.machine(),
        capabilities=capabilities,
        gpus=gpus,
        default_shell=get_default_shell(),
    )
