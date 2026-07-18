"""Typer CLI entry point."""
import typer

app = typer.Typer(
    name="cyberharness",
    help="Connectivity-aware AI harness. Run with no arguments to open the TUI.",
    no_args_is_help=False,
)

config_app = typer.Typer()
app.add_typer(config_app, name="config")


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo("cyberharness — TUI not yet wired (Plan 04)")
        raise typer.Exit(code=0)


@app.command()
def init() -> None:
    """Run the setup wizard manually."""
    typer.echo("not yet implemented (Plan 02)")
    raise typer.Exit(code=0)


@app.command()
def status() -> None:
    """Print workspace paths, config loaded, mode, version."""
    typer.echo("not yet implemented (Plan 03)")
    raise typer.Exit(code=0)


@app.command()
def probe() -> None:
    """Run one connectivity check and print result."""
    typer.echo("not yet implemented (Plan 03)")
    raise typer.Exit(code=0)


@app.command()
def bench() -> None:
    """Bench not yet implemented."""
    typer.echo("not yet implemented (Plan 04)")
    raise typer.Exit(code=0)


@config_app.command("show")
def config_show() -> None:
    """View config."""
    typer.echo("not yet implemented (Plan 02)")
    raise typer.Exit(code=0)


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Set a config value."""
    typer.echo("not yet implemented (Plan 02)")
    raise typer.Exit(code=0)
