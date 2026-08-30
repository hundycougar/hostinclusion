"""Command line interface for HostInclusion."""

from __future__ import annotations

import sys
from typing import Optional
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer

from hostinclusion.capabilities import get_node_info
from hostinclusion.client import run_interactive_session
from hostinclusion.daemon import start_daemon
from hostinclusion.discovery import list_tailscale_peers

app = typer.Typer(
    name="hostinclusion",
    help="HostInclusion: Distributed host daemon for remote terminal sessions and resource access over Tailscale.",
    no_args_is_help=True,
)
daemon_app = typer.Typer(help="Manage the HostInclusion background daemon.")
app.add_typer(daemon_app, name="daemon")

console = Console()


@daemon_app.command("start")
def daemon_start(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host/IP address"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    log_level: str = typer.Option("info", "--log-level", "-l", help="Logging level"),
) -> None:
    """Start the HostInclusion daemon service."""
    console.print(
        Panel.fit(
            f"[bold green]Starting HostInclusion Daemon[/bold green]\n"
            f"Host: [cyan]{host}[/cyan]\n"
            f"Port: [cyan]{port}[/cyan]\n"
            f"Terminal WebSocket: [yellow]ws://{host}:{port}/api/v1/terminal/ws[/yellow]",
            title="HostInclusion",
        )
    )
    start_daemon(host=host, port=port, log_level=log_level)


@app.command("info")
def node_info(
    host: Optional[str] = typer.Argument(None, help="Remote host to query (defaults to local host)"),
    port: int = typer.Option(8765, "--port", "-p", help="Daemon port"),
) -> None:
    """Show system information, capabilities, and GPU hardware."""
    if host is None or host in ("localhost", "127.0.0.1"):
        info = get_node_info()
    else:
        url = f"http://{host}:{port}/api/v1/info"
        try:
            resp = httpx.get(url, timeout=3.0)
            resp.raise_for_status()
            from hostinclusion.capabilities import NodeInfo
            info = NodeInfo.model_validate(resp.json())
        except Exception as e:
            console.print(f"[bold red]Failed to query node {host}:[/bold red] {e}")
            raise typer.Exit(1)

    table = Table(title=f"Node Information: {info.hostname}")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Hostname", info.hostname)
    table.add_row("Platform", f"{info.platform} ({info.os_version})")
    table.add_row("Architecture", info.architecture)
    table.add_row("Default Shell", info.default_shell)
    table.add_row("Capabilities", ", ".join(info.capabilities))

    if info.gpus:
        gpu_summary = "\n".join(
            f"- {g.name} ({g.memory_total_mb} MB total / {g.memory_free_mb} MB free, driver: {g.driver_version})"
            for g in info.gpus
        )
        table.add_row("GPUs", gpu_summary)
    else:
        table.add_row("GPUs", "[dim]None detected[/dim]")

    console.print(table)


@app.command("term")
@app.command("connect")
def terminal_connect(
    host: str = typer.Argument(..., help="Host address or Tailscale IP/DNS name to connect to"),
    port: int = typer.Option(8765, "--port", "-p", help="Daemon port"),
    cmd: Optional[str] = typer.Option(None, "--cmd", "-c", help="Custom command to run in PTY"),
) -> None:
    """Connect to a remote terminal session on a HostInclusion host."""
    try:
        run_interactive_session(host=host, port=port, command=cmd)
    except Exception as e:
        console.print(f"[bold red]Session error:[/bold red] {e}")
        sys.exit(1)


@app.command("peers")
def list_peers(
    probe_port: int = typer.Option(8765, "--port", "-p", help="Port to probe for HostInclusion daemon"),
) -> None:
    """List Tailscale network peers and detect active HostInclusion daemons."""
    with console.status("[bold green]Discovering Tailscale peers...[/bold green]"):
        peers = list_tailscale_peers(probe_port=probe_port)

    if not peers:
        console.print("[yellow]No Tailscale peers discovered (or Tailscale is not running).[/yellow]")
        return

    table = Table(title="Tailscale Network Peers")
    table.add_column("Hostname", style="cyan")
    table.add_column("Tailscale IP", style="magenta")
    table.add_column("OS", style="blue")
    table.add_column("Status", style="green")
    table.add_column("HostInclusion", style="bold yellow")
    table.add_column("Capabilities", style="white")

    for peer in peers:
        ip = peer.tailscale_ips[0] if peer.tailscale_ips else peer.dns_name
        status = "[green]Online[/green]" if peer.online else "[dim]Offline[/dim]"
        if peer.is_self:
            status += " (self)"

        hi_status = "[green]Active[/green]" if peer.hostinclusion_active else "[dim]Not responding[/dim]"
        caps = ""
        if peer.node_info and "capabilities" in peer.node_info:
            caps = ", ".join(peer.node_info["capabilities"])

        table.add_row(peer.hostname, ip, peer.os, status, hi_status, caps)

    console.print(table)


if __name__ == "__main__":
    app()
