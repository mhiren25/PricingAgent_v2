#!/usr/bin/env python3
"""
CLI interface for the Financial Trading Agent
Fixed to work with updated QueryParameters
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from typing import Optional
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from datetime import datetime

from src.graph.workflow import create_supervisor_graph
from src.models.state import AgentState
from src.models.query_parameters import QueryParameters
from src.utils.date_handler import DateHandler
from config.settings import settings

console = Console()


def create_initial_state(query: str) -> AgentState:
    """Create initial agent state"""
    return {
        "messages": [],
        "user_query": query,
        "parameters": QueryParameters(
            intent="Investigation",
            reasoning="Initial state"
        ),
        "investigation_step": 0,
        "findings": {},
        "comparison_findings": {},
        "final_answer": "",
        "sender": "",
        "current_investigation": "primary",
        "error_log": [],
        # Enrichment fields
        "aaa_order_id": None,
        "enrichment_flow": False,
        "actual_order_id": None
    }


def display_header():
    """Display CLI header"""
    console.print(Panel.fit(
        "[bold cyan]Financial Trading Data & Debugging Agent[/bold cyan]\n"
        "[dim]Multi-Agent System for Client Pricing Investigations[/dim]",
        border_style="cyan"
    ))


def display_agent_messages(state: AgentState):
    """Display agent conversation"""
    console.print("\n[bold yellow]═══ Agent Conversation ═══[/bold yellow]\n")
    
    for msg in state["messages"]:
        if hasattr(msg, 'name') and msg.name:
            if msg.name == "Supervisor":
                console.print(f"\n[bold blue]🎯 {msg.name}[/bold blue]")
            elif "Comparison" in msg.name:
                console.print(f"\n[bold magenta]🔍 {msg.name}[/bold magenta]")
            elif "Code" in msg.name:
                console.print(f"\n[bold green]💻 {msg.name}[/bold green]")
            elif "Summarization" in msg.name:
                console.print(f"\n[bold yellow]📝 {msg.name}[/bold yellow]")
            elif "Order_Enricher" in msg.name:
                console.print(f"\n[bold cyan]🔧 {msg.name}[/bold cyan]")
            else:
                console.print(f"\n[bold cyan]🤖 {msg.name}[/bold cyan]")
        
        console.print(msg.content)


def display_summary(state: AgentState):
    """Display execution summary"""
    table = Table(title="Execution Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    # Count agents used
    agents_used = set()
    for msg in state["messages"]:
        if hasattr(msg, 'name') and msg.name and msg.name != "Supervisor":
            agents_used.add(msg.name)
    
    params = state.get("parameters")
    table.add_row("Intent", params.intent if params else "Unknown")
    table.add_row("Agents Used", f"{len(agents_used)} agents")
    table.add_row("Agent Names", ", ".join(agents_used) if agents_used else "None")
    table.add_row("Total Messages", str(len(state["messages"])))
    table.add_row("Errors", str(len(state.get("error_log", []))))
    
    if params and params.order_id:
        table.add_row("Order ID", params.order_id)
        if params.date:
            table.add_row("Date", params.date)
    
    if params and params.comparison_order_id:
        table.add_row("Comparison Order", params.comparison_order_id)
        if params.comparison_date:
            table.add_row("Comparison Date", params.comparison_date)
    
    # Show enrichment if it happened
    if state.get("actual_order_id"):
        table.add_row("Enriched Order ID", state["actual_order_id"])
    
    console.print("\n")
    console.print(table)


def run_interactive_mode():
    """Run agent in interactive mode"""
    display_header()
    
    console.print("\n[bold green]Interactive Mode[/bold green]")
    console.print("[dim]Type 'exit' or 'quit' to exit, 'help' for examples[/dim]\n")
    
    # Create agent once
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Initializing agent system...", total=None)
        agent = create_supervisor_graph()
        progress.update(task, completed=True)
    
    console.print("[green]✓[/green] Agent system ready!\n")
    
    # Example queries
    examples = [
        "How does client pricing work for GOLD tier clients?",
        "Show me logs for order ABC123 on date 2025-01-15",
        "Investigate order XYZ789 from 2025-01-20",
        "Investigate order D12.345.678 on 12/10/2025",
        "Compare order ABC123 from yesterday with DEF456",
        "Compare order D11111111 with ORD222222 on 2025-10-12",
        "How does the pricing calculation work in the Java code?",
        "What's the current health of the pricing service?"
    ]
    
    while True:
        try:
            query = console.input("\n[bold cyan]Query>[/bold cyan] ")
            
            if not query.strip():
                continue
            
            if query.lower() in ['exit', 'quit', 'q']:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            
            if query.lower() == 'help':
                console.print("\n[bold]Example Queries:[/bold]")
                for i, example in enumerate(examples, 1):
                    console.print(f"  {i}. {example}")
                continue
            
            if query.lower() == 'clear':
                console.clear()
                display_header()
                continue
            
            # Execute query
            console.print(f"\n[dim]Processing: {query}[/dim]\n")
            
            start_time = datetime.now()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Investigating...", total=None)
                
                state = create_initial_state(query)
                result = agent.invoke(state)
                
                progress.update(task, completed=True)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Display results
            display_agent_messages(result)
            display_summary(result)
            
            console.print(f"\n[dim]Completed in {duration:.2f} seconds[/dim]")
            
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error: {str(e)}[/red]")
            import traceback
            if "--debug" in sys.argv:
                console.print(f"[dim]{traceback.format_exc()}[/dim]")


def run_single_query(query: str, output_format: str = "pretty"):
    """Run a single query"""
    console.print(f"\n[cyan]Query:[/cyan] {query}\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Initializing agent...", total=None)
        agent = create_supervisor_graph()
        progress.update(task, description="[cyan]Executing query...")
        
        state = create_initial_state(query)
        result = agent.invoke(state)
        
        progress.update(task, completed=True)
    
    if output_format == "json":
        import json
        params = result.get("parameters")
        output = {
            "query": query,
            "intent": params.intent if params else None,
            "order_id": params.order_id if params else None,
            "date": params.date if params else None,
            "comparison_order_id": params.comparison_order_id if params else None,
            "comparison_date": params.comparison_date if params else None,
            "enriched_order_id": result.get("actual_order_id"),
            "final_answer": result.get("final_answer", ""),
            "agents_used": list(set(
                msg.name for msg in result["messages"] 
                if hasattr(msg, 'name') and msg.name
            )),
            "errors": result.get("error_log", [])
        }
        console.print_json(data=output)
    elif output_format == "markdown":
        md = Markdown(result.get("final_answer", "No answer generated"))
        console.print(md)
    else:  # pretty
        display_agent_messages(result)
        display_summary(result)


def run_batch_mode(file_path: str):
    """Run queries from a file"""
    console.print(f"\n[cyan]Batch Mode:[/cyan] {file_path}\n")
    
    if not os.path.exists(file_path):
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        return
    
    with open(file_path, 'r') as f:
        queries = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    console.print(f"[green]Found {len(queries)} queries[/green]\n")
    
    # Initialize agent once
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Initializing agent...", total=None)
        agent = create_supervisor_graph()
        progress.update(task, completed=True)
    
    results = []
    
    for i, query in enumerate(queries, 1):
        console.print(f"\n[bold cyan]Query {i}/{len(queries)}:[/bold cyan] {query}")
        
        try:
            state = create_initial_state(query)
            result = agent.invoke(state)
            
            results.append({
                "query": query,
                "success": True,
                "answer": result.get("final_answer", "")
            })
            
            console.print("[green]✓ Completed[/green]")
            
        except Exception as e:
            console.print(f"[red]✗ Error: {str(e)}[/red]")
            results.append({
                "query": query,
                "success": False,
                "error": str(e)
            })
    
    # Summary
    success_count = sum(1 for r in results if r.get("success"))
    console.print(f"\n[bold]Batch Summary:[/bold]")
    console.print(f"  Total: {len(queries)}")
    console.print(f"  [green]Success: {success_count}[/green]")
    console.print(f"  [red]Failed: {len(queries) - success_count}[/red]")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Financial Trading Data & Debugging Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python run_agent.py
  
  # Single query
  python run_agent.py -q "Investigate order ABC123 from 2025-01-15"
  
  # Single query with date normalization
  python run_agent.py -q "Investigate order D12.345.678 on 12/10/2025"
  
  # Single query with JSON output
  python run_agent.py -q "Show logs for order ABC123" -f json
  
  # Batch mode
  python run_agent.py -b queries.txt
  
  # Show configuration
  python run_agent.py --show-config
        """
    )
    
    parser.add_argument(
        '-q', '--query',
        type=str,
        help='Execute a single query'
    )
    
    parser.add_argument(
        '-b', '--batch',
        type=str,
        help='Execute queries from a file (one per line)'
    )
    
    parser.add_argument(
        '-f', '--format',
        type=str,
        choices=['pretty', 'json', 'markdown'],
        default='pretty',
        help='Output format (default: pretty)'
    )
    
    parser.add_argument(
        '--show-config',
        action='store_true',
        help='Show current configuration'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    # Show configuration
    if args.show_config:
        table = Table(title="Current Configuration", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Environment", settings.app_env)
        table.add_row("Supervisor Model", settings.supervisor_model)
        table.add_row("Agent Model", settings.agent_model)
        table.add_row("Cheap Model", settings.cheap_model)
        table.add_row("Reflection Enabled", str(settings.enable_reflection))
        table.add_row("Caching Enabled", str(settings.enable_caching))
        table.add_row("Cache TTL (min)", str(settings.cache_ttl_minutes))
        table.add_row("Max Retries", str(settings.max_retries))
        table.add_row("Timeout (sec)", str(settings.timeout_seconds))
        table.add_row("Code Agent", str(settings.enable_code_agent))
        table.add_row("Comparison Agent", str(settings.enable_comparison_agent))
        table.add_row("Current Date", DateHandler.get_current_date())
        
        console.print(table)
        return
    
    # Execute based on mode
    if args.query:
        display_header()
        run_single_query(args.query, args.format)
    elif args.batch:
        display_header()
        run_batch_mode(args.batch)
    else:
        # Interactive mode
        run_interactive_mode()


if __name__ == "__main__":
    main()
