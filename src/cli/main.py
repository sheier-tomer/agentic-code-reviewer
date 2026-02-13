from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.syntax import Syntax

from src.agent.state import AgentState, Decision, TaskType
from src.agent.graph import build_graph

app = typer.Typer(name="kilo", help="Agentic AI Code Reviewer")
console = Console()


@app.command()
def review(
    repo_path: Path = typer.Argument(..., help="Path to the repository to review"),
    task: str = typer.Option(..., "--task", "-t", help="Task description"),
    task_type: str = typer.Option("review", "--type", help="Task type: refactor, bugfix, or review"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for diff"),
):
    """Run an AI-powered code review on a repository."""
    task_type_enum = TaskType(task_type.lower())
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Running code review...", total=None)
        
        state = AgentState.create(
            repo_path=str(repo_path),
            task_type=task_type_enum,
            task_description=task,
        )
        
        graph = build_graph()
        final_state = graph.invoke(state)
    
    _display_results(final_state, output)


@app.command()
def index(
    repo_path: Path = typer.Argument(..., help="Path to the repository to index"),
):
    """Index a repository for code retrieval."""
    import asyncio
    from src.indexing import ingest_repository
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Indexing repository...", total=None)
        
        chunks, manifest = asyncio.run(ingest_repository(repo_path))
    
    console.print(f"\n[green]Indexed {len(chunks)} code chunks from {len(manifest)} files[/green]")
    
    table = Table(title="Index Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Files", str(len(manifest)))
    table.add_row("Code Chunks", str(len(chunks)))
    table.add_row("Total Size", f"{sum(f['size'] for f in manifest):,} bytes")
    
    console.print(table)


@app.command()
def check(
    repo_path: Path = typer.Argument(..., help="Path to the repository"),
    run_tests: bool = typer.Option(True, "--tests/--no-tests", help="Run tests"),
    run_lint: bool = typer.Option(True, "--lint/--no-lint", help="Run linting"),
    run_typecheck: bool = typer.Option(True, "--typecheck/--no-typecheck", help="Run type checking"),
    run_security: bool = typer.Option(True, "--security/--no-security", help="Run security scan"),
):
    """Run validation checks on a repository."""
    import asyncio
    from src.validation import ValidationPipeline, ValidationConfig
    
    config = ValidationConfig(
        run_tests=run_tests,
        run_lint=run_lint,
        run_typecheck=run_typecheck,
        run_security=run_security,
    )
    
    pipeline = ValidationPipeline(config)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Running validation checks...", total=None)
        results = asyncio.run(pipeline.run(cwd=str(repo_path)))
    
    table = Table(title="Validation Results")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Errors")
    table.add_column("Warnings")
    table.add_column("Duration")
    
    for name, result in results.items():
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        table.add_row(
            name,
            status,
            str(result.error_count),
            str(result.warning_count),
            f"{result.duration_ms}ms",
        )
    
    console.print(table)
    
    summary = pipeline.get_summary(results)
    if summary["all_passed"]:
        console.print("\n[green]All checks passed![/green]")
    else:
        console.print(f"\n[red]{summary['failed']} check(s) failed[/red]")


@app.command()
def runs():
    """List recent agent runs."""
    import asyncio
    from datetime import datetime
    from sqlalchemy import select
    from src.db.models import AgentRun, async_session
    
    async def get_runs():
        async with async_session() as db:
            result = await db.execute(
                select(AgentRun)
                .order_by(AgentRun.created_at.desc())
                .limit(20)
            )
            return result.scalars().all()
    
    runs_list = asyncio.run(get_runs())
    
    table = Table(title="Recent Runs")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Decision")
    table.add_column("Quality")
    table.add_column("Risk")
    table.add_column("Created")
    
    for run in runs_list:
        status_color = {
            "pending": "yellow",
            "running": "blue",
            "completed": "green",
            "failed": "red",
        }.get(run.status, "white")
        
        decision_str = run.decision or "-"
        if run.decision == "auto_approve":
            decision_str = "[green]auto-approve[/green]"
        elif run.decision == "needs_review":
            decision_str = "[yellow]needs-review[/yellow]"
        elif run.decision == "reject":
            decision_str = "[red]reject[/red]"
        
        table.add_row(
            str(run.id)[:8],
            run.task_type,
            f"[{status_color}]{run.status}[/{status_color}]",
            decision_str,
            f"{run.quality_score:.1f}" if run.quality_score else "-",
            f"{run.risk_score:.2f}" if run.risk_score else "-",
            run.created_at.strftime("%Y-%m-%d %H:%M") if run.created_at else "-",
        )
    
    console.print(table)


def _display_results(state: AgentState, output: Optional[Path] = None):
    console.print()
    
    decision_color = {
        Decision.AUTO_APPROVE: "green",
        Decision.NEEDS_REVIEW: "yellow",
        Decision.REJECT: "red",
    }.get(state.decision, "white")
    
    console.print(Panel(
        f"[bold]Decision:[/bold] [{decision_color}]{state.decision.value}[/{decision_color}]\n"
        f"[bold]Quality Score:[/bold] {state.quality_score:.1f}/100\n"
        f"[bold]Risk Score:[/bold] {state.risk_score:.2f}",
        title="Review Results",
        border_style=decision_color,
    ))
    
    if state.explanation:
        console.print(Panel(state.explanation, title="Explanation"))
    
    if state.generated_diff:
        console.print("\n[bold]Generated Diff:[/bold]")
        syntax = Syntax(state.generated_diff, "diff", theme="monokai")
        console.print(syntax)
        
        if output:
            output.write_text(state.generated_diff)
            console.print(f"\n[green]Diff written to {output}[/green]")
    
    if state.errors:
        console.print("\n[red]Errors:[/red]")
        for error in state.errors:
            console.print(f"  - {error}")


if __name__ == "__main__":
    app()
