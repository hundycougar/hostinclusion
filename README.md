# HostInclusion

HostInclusion is a lightweight distributed host daemon that runs across Tailscale-connected machines to provide remote PTY terminal sessions and distributed local resource access (including local GPU AI processing on machines with dedicated hardware like NVIDIA RTX 4070).

## Features

- **Interactive Remote Terminal Sessions**: Bi-directional PTY streaming over WebSockets with ANSI color support, raw mode, and dynamic terminal window resizing (`SIGWINCH`).
- **Tailscale Mesh Integration**: Peer discovery across your tailnet and automatic HostInclusion daemon probing.
- **Hardware & Capability Detection**: Auto-detects system specifications and NVIDIA GPUs (`nvidia-smi` / CUDA capabilities).
- **Extensible Architecture**: Built with FastAPI and `asyncio`, designed to support upcoming GPU AI inference workers (vLLM / PyTorch offloading).

## Quickstart

### 1. Installation

```bash
# Clone and enter directory
cd ~/dev/hostinclusion

# Create virtual environment and install
uv venv
uv pip install -e ".[dev]"
```

### 2. Start the Daemon on a Host

Run this on any machine in your Tailscale network:

```bash
# Start listening on all interfaces (port 8765 by default)
uv run hostinclusion daemon start --host 0.0.0.0 --port 8765
```

### 3. Check Host Info & Hardware

```bash
# Local host info
uv run hostinclusion info

# Remote host info
uv run hostinclusion info <tailscale-ip-or-dns>
```

### 4. Connect to an Interactive Terminal Session

```bash
# Connect to default shell on remote host
uv run hostinclusion term <tailscale-ip-or-dns>

# Connect with a specific command
uv run hostinclusion term <tailscale-ip-or-dns> --cmd /bin/bash
```

### 5. Discover Tailscale Peers

```bash
# Scan Tailscale network and detect running HostInclusion daemons
uv run hostinclusion peers
```

## Running Tests

```bash
uv run pytest
```
