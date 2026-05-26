"""`uia-agent` command-line surface.

Two subcommands:

  uia-agent dump --app <name>                 print pruned UIA tree as JSON
  uia-agent run  --app <name> "<instruction>" drive the app to satisfy intent

Streams one line per agent step so the user sees what the LLM chose and why.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from . import __version__
from .agent import AgentBudgetExceeded, MAX_STEPS_DEFAULT, run
from .uia_tree import count_nodes, snapshot, to_json


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Drive Windows thick-client apps via the UIA accessibility tree.",
)


@app.command()
def dump(
    app_name: Annotated[
        str,
        typer.Option("--app", help="Window title or class name substring (case-insensitive)."),
    ],
    indent: Annotated[
        int,
        typer.Option("--indent", help="JSON indent; pass 0 for compact."),
    ] = 2,
    summary: Annotated[
        bool,
        typer.Option("--summary/--no-summary", help="Print node count to stderr."),
    ] = True,
) -> None:
    """Print the focused window's pruned UIA tree as JSON (debug aid)."""
    try:
        tree = snapshot(app_name)
    except Exception as exc:
        typer.echo(f"snapshot failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(to_json(tree, indent=indent or None))
    if summary:
        typer.echo(f"[{count_nodes(tree)} nodes]", err=True)


@app.command("run")
def run_cmd(
    instruction: Annotated[
        str,
        typer.Argument(help="Natural-language goal, e.g. \"type a haiku and save as poem.txt\"."),
    ],
    app_name: Annotated[
        str,
        typer.Option("--app", help="Window title or class name substring (case-insensitive)."),
    ],
    max_steps: Annotated[
        int,
        typer.Option("--max-steps", help="Hard cap on the observe→act loop."),
    ] = MAX_STEPS_DEFAULT,
) -> None:
    """Drive the focused app toward the instruction, streaming each step."""
    try:
        for event in run(app_name, instruction, max_steps=max_steps):
            _emit(event)
    except AgentBudgetExceeded as exc:
        typer.echo(f"\n[budget] {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except KeyboardInterrupt:
        typer.echo("\n[interrupted]", err=True)
        raise typer.Exit(code=130) from None
    except Exception as exc:
        typer.echo(f"\n[error] {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(f"uia-agent {__version__}")


def _emit(event: object) -> None:
    """Format one StepEvent as a single readable line on stdout."""
    # Late import keeps the module importable without uiautomation at install time.
    from .agent import StepEvent

    if not isinstance(event, StepEvent):
        return
    action = event.action
    head = f"step {event.index:02d}  {action.kind:<6}"
    target = f" → {action.target_id}" if action.target_id else ""
    payload = f"  text={action.text!r}" if action.text else ""
    suffix: str
    if event.error is not None:
        suffix = f"  ✗ {event.error}"
    elif event.result is not None:
        suffix = f"  ✓ {event.result.detail}"
    else:
        suffix = ""
    typer.echo(f"{head}{target}{payload}{suffix}")
    if action.reason:
        typer.echo(f"            why: {action.reason}")
    sys.stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    app()
