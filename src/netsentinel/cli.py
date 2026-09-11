"""``netsentinel`` command-line entry point."""

from __future__ import annotations

import secrets

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import get_settings

app = typer.Typer(add_completion=False, help="NetSentinel - distributed home-network monitor.")
console = Console()


@app.command()
def version() -> None:
    """Print the version and exit."""
    console.print(f"net-sentinel {__version__}")


@app.command("gen-token")
def gen_token() -> None:
    """Print a fresh random API token for the hub<->sensor link."""
    console.print(secrets.token_hex(32))


@app.command()
def config() -> None:
    """Show the effective configuration (secrets masked)."""
    s = get_settings()
    t = Table(title="NetSentinel configuration", show_header=False)
    masked = {"api_token", "abuseipdb_api_key", "telegram_bot_token", "dashboard_password"}
    for key, val in s.model_dump().items():
        shown = "********" if key in masked and val else str(val)
        t.add_row(key, shown)
    console.print(t)


@app.command()
def hub(
    host: str = typer.Option(None, help="Override bind host."),
    port: int = typer.Option(None, help="Override bind port."),
    reload: bool = typer.Option(False, help="Auto-reload (development only)."),
) -> None:
    """Run the hub (API + dashboard)."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "netsentinel.hub.app:app",
        host=host or s.hub_host,
        port=port or s.hub_port,
        reload=reload,
        log_level=s.log_level.lower(),
    )


@app.command()
def sensor() -> None:
    """Run the sensor (collectors + hub uplink)."""
    from .sensor.runner import main

    main()


@app.command("test-alert")
def test_alert(
    severity: str = typer.Option("medium", help="info|low|medium|high"),
) -> None:
    """Send a test notification through the configured backend."""
    from .notify import Notifier

    ok = Notifier().send(
        "NetSentinel test alert",
        "If you can read this, notifications work.",
        severity,
    )
    console.print("[green]delivered[/green]" if ok else "[red]delivery failed[/red] (check logs)")


@app.command()
def selftest() -> None:
    """Initialise the database and verify the install is importable."""
    from .db import init_db

    init_db()
    s = get_settings()
    console.print(f"[green]OK[/green] db ready at {s.db_path}")
    console.print(f"role={s.role}  notify={s.notify_backend}  hub_url={s.hub_url}")


if __name__ == "__main__":
    app()
