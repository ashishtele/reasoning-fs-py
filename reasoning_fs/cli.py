"""CLI interface for ReasoningFS."""

import typer
from typing import Optional

from .memory import ReasoningMemory
from .vfs import ChromaFs
from .scaling import ConfidenceScaler

app = typer.Typer(help="ReasoningFS - Memory-aware agent harness")


@app.command()
def init(
    memory_path: str = typer.Option("reasoning_db", "--memory", "-m", help="Memory DB path"),
    vfs_path: str = typer.Option("vfs_db", "--vfs", "-v", help="VFS DB path"),
):
    """Initialize ReasoningFS databases."""
    memory = ReasoningMemory(db_path=memory_path)
    vfs = ChromaFs(db_path=vfs_path)
    
    typer.echo(f"✅ Initialized memory at {memory_path}")
    typer.echo(f"✅ Initialized VFS at {vfs_path}")


@app.command()
def store(
    task: str = typer.Argument(..., help="Task description"),
    reasoning: str = typer.Argument(..., help="Reasoning steps"),
    outcome: str = typer.Argument(..., help="Outcome"),
    success: bool = typer.Option(True, "--success", "-s", help="Success status"),
    memory_path: str = typer.Option("reasoning_db", "--memory", "-m", help="Memory DB path"),
):
    """Store a reasoning trace."""
    memory = ReasoningMemory(db_path=memory_path)
    trace_id = memory.store(
        task=task,
        reasoning=reasoning,
        outcome=outcome,
        success=success,
    )
    typer.echo(f"✅ Stored trace: {trace_id}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    n_results: int = typer.Option(5, "--n", "-n", help="Number of results"),
    memory_path: str = typer.Option("reasoning_db", "--memory", "-m", help="Memory DB path"),
):
    """Search for similar reasoning traces."""
    memory = ReasoningMemory(db_path=memory_path)
    traces = memory.search(query, n_results=n_results)
    
    typer.echo(f"🔎 Found {len(traces)} traces:\n")
    for i, trace in enumerate(traces, 1):
        typer.echo(f"{i}. Task: {trace.task}")
        typer.echo(f"   Reasoning: {trace.reasoning[:100]}...")
        typer.echo(f"   Outcome: {trace.outcome}")
        typer.echo(f"   Success: {trace.success}\n")


@app.command()
def write(
    command: str = typer.Argument(..., help="Write command (path=content)"),
    vfs_path: str = typer.Option("vfs_db", "--vfs", "-v", help="VFS DB path"),
):
    """Write a file to VFS."""
    vfs = ChromaFs(db_path=vfs_path)
    result = vfs.write(command)
    typer.echo(f"✅ {result}")


@app.command()
def cat(
    path: str = typer.Argument(..., help="File path"),
    vfs_path: str = typer.Option("vfs_db", "--vfs", "-v", help="VFS DB path"),
):
    """Read a file from VFS."""
    vfs = ChromaFs(db_path=vfs_path)
    content = vfs.cat(path)
    typer.echo(content)


@app.command()
def grep(
    pattern: str = typer.Argument(..., help="Pattern to search"),
    vfs_path: str = typer.Option("vfs_db", "--vfs", "-v", help="VFS DB path"),
):
    """Search for pattern in VFS."""
    vfs = ChromaFs(db_path=vfs_path)
    result = vfs.grep(pattern)
    typer.echo(result)


@app.command()
def ls(
    path: str = typer.Argument(".", help="Directory path"),
    vfs_path: str = typer.Option("vfs_db", "--vfs", "-v", help="VFS DB path"),
):
    """List files in VFS."""
    vfs = ChromaFs(db_path=vfs_path)
    result = vfs.ls(path)
    typer.echo(result)


@app.command()
def scale(
    confidence: float = typer.Argument(..., help="Confidence score (0.0-1.0)"),
):
    """Get scaling parameters for confidence."""
    scaler = ConfidenceScaler()
    params = scaler.scale(confidence)
    recommendation = scaler.get_recommendation(confidence)
    
    typer.echo(f"📊 Scaling parameters for confidence={confidence:.2f}:")
    typer.echo(f"   Max tokens: {params.max_tokens}")
    typer.echo(f"   Temperature: {params.temperature}")
    typer.echo(f"   Top-p: {params.top_p}")
    typer.echo(f"\n💡 {recommendation}")


@app.command()
def stats(
    memory_path: str = typer.Option("reasoning_db", "--memory", "-m", help="Memory DB path"),
    vfs_path: str = typer.Option("vfs_db", "--vfs", "-v", help="VFS DB path"),
):
    """Show statistics for memory and VFS."""
    memory = ReasoningMemory(db_path=memory_path)
    vfs = ChromaFs(db_path=vfs_path)
    
    memory_stats = memory.stats()
    vfs_stats = vfs.stats()
    
    typer.echo("📊 ReasoningFS Statistics:")
    typer.echo(f"   Memory: {memory_stats['total_traces']} traces")
    typer.echo(f"   VFS: {vfs_stats['total_files']} files")


if __name__ == "__main__":
    app()
