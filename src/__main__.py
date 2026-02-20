"""CLI entry point: `python -m src serve` or `python -m src chat`."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer(help="Bright Data Web Research Agent")
console = Console()


@app.command()
def serve(port: int = 8000, host: str = "0.0.0.0"):
    """Start the web UI server."""
    import uvicorn

    from src.web.app import create_app

    console.print(f"[bold green]Starting server on {host}:{port}[/]")
    web_app = create_app()
    uvicorn.run(web_app, host=host, port=port)


@app.command()
def chat():
    """Interactive chat with the agent in the terminal."""
    from src.agent.loop import process_message
    from src.agent.models import Conversation

    conversation = Conversation()
    console.print("[bold cyan]Bright Data Chat Agent[/]")
    console.print("[dim]Type your message, or 'quit' to exit.[/]\n")

    while True:
        try:
            user_input = console.input("[bold green]You:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            break

        conversation.add_user_message(user_input)
        conversation.is_processing = True

        console.print("[dim]Thinking...[/]")
        process_message(conversation)
        conversation.is_processing = False

        # Display new messages (skip the user message we just added)
        for msg in conversation.messages:
            if msg.role == "assistant" and msg == conversation.messages[-1]:
                console.print(f"\n[bold blue]Assistant:[/]")
                console.print(Markdown(msg.content))
            elif msg.role == "tool_activity" and not hasattr(msg, "_displayed"):
                console.print(f"  [yellow]→ {msg.tool_name}[/] [dim]({msg.tool_duration_ms}ms)[/]")
                msg._displayed = True
            elif msg.role == "file" and not hasattr(msg, "_displayed"):
                console.print(f"  [bold green]📄 {msg.filename}[/] ({msg.file_size:,} bytes)")
                msg._displayed = True
            elif msg.role == "system" and not hasattr(msg, "_displayed"):
                console.print(f"  [bold red]⚠ {msg.content}[/]")
                msg._displayed = True

        console.print()


if __name__ == "__main__":
    app()
