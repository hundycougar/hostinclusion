# HostInclusion

HostInclusion is a lightweight distributed host daemon running across Tailscale-connected machines to provide remote PTY terminal sessions and distributed local resource sharing (e.g. GPU AI inference offloading).

## Topology & Deployment Context

- **Host Environment**: Hermes runs on a hosted VPS server.
- **Client Access**: The user connects to Hermes through the web browser dashboard and other clients over Tailscale.
- **In-Browser Terminal**: Remote terminal sessions to any Tailscale host (e.g. CachyOS box, GPU rigs, local machines) are rendered directly inside the Hermes web dashboard browser tab, proxied via the Hermes VPS gateway for seamless in-session access.

## Running and testing

```bash
# install dependencies
uv venv
uv pip install -e ".[dev]"

# run tests
uv run pytest

# run the host inclusion daemon locally
uv run python -m hostinclusion.daemon
```

## Decisions that must not change silently

- **Runtime & Language**: Python 3.11+ managed with `uv` for seamless PyTorch / CUDA / vLLM compatibility on GPU nodes.
- **Networking & Transport**: Tailscale mesh for node discovery, secure transport, and peer authentication.
- **Terminal Sessions**: PTY allocation via `ptyprocess` (Linux/macOS) / `pywinpty` (Windows) streamed over WebSocket endpoints via FastAPI.
- **Architecture**:
  - `hostinclusion.daemon`: Daemon service running on each node exposing status and WebSocket PTY sessions.
  - `hostinclusion.cli`: CLI to list connected nodes and connect to remote terminal sessions.
  - Pluggable capability modules: `terminal` (MVP), extensible to `gpu_worker` / `inference` (e.g. RTX 4070 offload).

## Knowledge pointers

Read `~/knowledge/index.md` first — it is the map. Follow links to what the task
needs; do not preload. These are pointers, not content.

- `~/knowledge/concepts/` — cross-domain concepts, interlinked
- `~/knowledge/domains/ai-engineering/index.md` — agent and context patterns

This section is here because it is not inherited. `~/dev/AGENTS.md` does not load
inside a project repo — discovery stops at this repo's git root — so every project
carries its own copy of these pointers.

## Model tier

Default is Tier 2 (Gemini Flash). Escalate to Tier 3 (Claude) only for
architecture decisions, multi-document synthesis, or debugging that has already
failed once at Tier 2. Never run background or bulk work at Tier 3.

## Conventions

- Tests accompany features. A change that cannot be demonstrated is not done.
- Smallest change that solves the problem. No speculative abstraction.
- Secrets live in an ignored env file, never in source.
- Match the surrounding style over any personal preference.
