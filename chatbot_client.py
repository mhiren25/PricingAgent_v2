"""
Example client for the Intelligent Chatbot API
Demonstrates various usage patterns and features
"""

import requests
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table

console = Console()

class ChatbotClient:
    """Client for interacting with the intelligent chatbot API"""
    
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
        
    def chat(self, message: str, show_intent: bool = True) -> dict:
        """
        Send a message to the chatbot
        
        Args:
            message: User's message
            show_intent: Display intent classification info
            
        Returns:
            Full response from API
        """
        payload = {"message": message}
        
        if self.session_id:
            payload["session_id"] = self.session_id
        
        response = requests.post(f"{self.base_url}/chat", json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        # Store session ID for continuity
        if not self.session_id:
            self.session_id = data["session_id"]
            console.print(f"[dim]Session created: {self.session_id}[/dim]\n")
        
        # Display intent classification
        if show_intent and data.get("intent"):
            intent = data["intent"]
            console.print(f"[dim]🎯 Intent: {intent['action_type']} "
                         f"(confidence: {intent['confidence']:.2f})[/dim]")
            console.print(f"[dim]💡 Reasoning: {intent['reasoning']}[/dim]\n")
        
        return data
    
    def classify_query(self, message: str) -> dict:
        """
        Classify a query without executing it
        
        Useful for previewing what action will be taken
        """
        params = {"message": message}
        
        if self.session_id:
            params["session_id"] = self.session_id
        
        response = requests.post(f"{self.base_url}/chat/classify", params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_session_info(self) -> dict:
        """Get current session information"""
        if not self.session_id:
            console.print("[yellow]No active session[/yellow]")
            return {}
        
        response = requests.get(f"{self.base_url}/chat/session/{self.session_id}")
        response.raise_for_status()
        
        return response.json()
    
    def clear_context(self):
        """Clear investigation context"""
        if not self.session_id:
            console.print("[yellow]No active session[/yellow]")
            return
        
        response = requests.post(f"{self.base_url}/chat/session/{self.session_id}/clear")
        response.raise_for_status()
        
        console.print("[green]✓ Context cleared[/green]")
    
    def get_history(self, limit: int = 10) -> dict:
        """Get conversation history"""
        if not self.session_id:
            console.print("[yellow]No active session[/yellow]")
            return {}
        
        response = requests.get(
            f"{self.base_url}/chat/session/{self.session_id}/history",
            params={"limit": limit}
        )
        response.raise_for_status()
        
        return response.json()
    
    def list_all_sessions(self) -> dict:
        """List all active sessions"""
        response = requests.get(f"{self.base_url}/chat/sessions")
        response.raise_for_status()
        
        return response.json()
    
    def display_response(self, data: dict):
        """Display chatbot response in a nice format"""
        response_text = data.get("response", "")
        response_type = data.get("response_type", "unknown")
        duration = data.get("duration_seconds", 0)
        
        # Choose emoji based on response type
        type_emoji = {
            "investigation": "🔍",
            "context_answer": "💬",
            "single_agent": "⚡",
            "clarification": "❓",
            "decline": "🚫"
        }.get(response_type, "🤖")
        
        console.print(f"\n{type_emoji} [bold green]Bot Response[/bold green] "
                     f"[dim]({duration:.2f}s)[/dim]\n")
        
        # Render markdown
        md = Markdown(response_text)
        console.print(md)
        console.print()
    
    def display_session_info(self, info: dict):
        """Display session information in a table"""
        table = Table(title="Session Information", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Session ID", info.get("session_id", "N/A"))
        table.add_row("Created", info.get("created_at", "N/A"))
        table.add_row("Last Activity", info.get("last_activity", "N/A"))
        table.add_row("Messages", str(info.get("message_count", 0)))
        table.add_row("Investigations", str(info.get("investigation_count", 0)))
        table.add_row("Context Available", "Yes" if info.get("context_available") else "No")
        
        if info.get("current_context"):
            ctx = info["current_context"]
            table.add_row("Current Order", ctx.get("order_id", "N/A"))
            table.add_row("Order Date", ctx.get("date", "N/A"))
        
        console.print(table)


def example_investigation_flow():
    """
    Example 1: Full investigation flow with follow-up questions
    """
    console.print(Panel.fit(
        "[bold cyan]Example 1: Investigation with Follow-ups[/bold cyan]",
        border_style="cyan"
    ))
    
    client = ChatbotClient()
    
    # Step 1: Initial investigation
    console.print("\n[bold]User:[/bold] Investigate order D12345678")
    response = client.chat("Investigate order D12345678")
    client.display_response(response)
    
    # Step 2: Follow-up question about failure
    console.print("\n[bold]User:[/bold] Why did it fail?")
    response = client.chat("Why did it fail?")
    client.display_response(response)
    
    # Step 3: Follow-up about pricing
    console.print("\n[bold]User:[/bold] What was the spread used?")
    response = client.chat("What was the spread used?")
    client.display_response(response)
    
    # Show session info
    console.print("\n[bold cyan]Session Info:[/bold cyan]")
    info = client.get_session_info()
    client.display_session_info(info)


def example_knowledge_query():
    """
    Example 2: Knowledge base queries (no investigation needed)
    """
    console.print(Panel.fit(
        "[bold cyan]Example 2: Knowledge Queries[/bold cyan]",
        border_style="cyan"
    ))
    
    client = ChatbotClient()
    
    # Query about FX pricing
    console.print("\n[bold]User:[/bold] How does FX pricing work?")
    response = client.chat("How does FX pricing work?")
    client.display_response(response)
    
    # Query about order types
    console.print("\n[bold]User:[/bold] What are the different order types?")
    response = client.chat("What are the different order types?")
    client.display_response(response)


def example_code_analysis():
    """
    Example 3: Code analysis queries
    """
    console.print(Panel.fit(
        "[bold cyan]Example 3: Code Analysis[/bold cyan]",
        border_style="cyan"
    ))
    
    client = ChatbotClient()
    
    # Code query
    console.print("\n[bold]User:[/bold] Show me the spread calculation code")
    response = client.chat("Show me the spread calculation code")
    client.display_response(response)
    
    # Follow-up about specific function
    console.print("\n[bold]User:[/bold] How does the calculate_final_price function work?")
    response = client.chat("How does the calculate_final_price function work?")
    client.display_response(response)


def example_reinvestigation_decline():
    """
    Example 4: Attempting to re-investigate same order (should be declined)
    """
    console.print(Panel.fit(
        "[bold cyan]Example 4: Re-investigation Prevention[/bold cyan]",
        border_style="cyan"
    ))
    
    client = ChatbotClient()
    
    # Initial investigation
    console.print("\n[bold]User:[/bold] Investigate order D12345678")
    response = client.chat("Investigate order D12345678")
    client.display_response(response)
    
    # Try to re-investigate same order
    console.print("\n[bold]User:[/bold] Investigate order D12345678 again")
    response = client.chat("Investigate order D12345678 again")
    client.display_response(response)
    
    # Clear context and retry
    console.print("\n[bold]User:[/bold] clear")
    client.clear_context()
    
    console.print("\n[bold]User:[/bold] Investigate order D12345678")
    response = client.chat("Investigate order D12345678")
    client.display_response(response)


def example_comparison_flow():
    """
    Example 5: Order comparison with follow-ups
    """
    console.print(Panel.fit(
        "[bold cyan]Example 5: Order Comparison[/bold cyan]",
        border_style="cyan"
    ))
    
    client = ChatbotClient()
    
    # Comparison investigation
    console.print("\n[bold]User:[/bold] Compare order D12345678 from today with D87654321 from yesterday")
    response = client.chat("Compare order D12345678 from today with D87654321 from yesterday")
    client.display_response(response)
    
    # Follow-up about differences
    console.print("\n[bold]User:[/bold] What caused the price difference?")
    response = client.chat("What caused the price difference?")
    client.display_response(response)
    
    # Follow-up about configuration
    console.print("\n[bold]User:[/bold] Were there any configuration differences?")
    response = client.chat("Were there any configuration differences?")
    client.display_response(response)


def example_query_classification():
    """
    Example 6: Preview query classification without execution
    """
    console.print(Panel.fit(
        "[bold cyan]Example 6: Query Classification Preview[/bold cyan]",
        border_style="cyan"
    ))
    
    client = ChatbotClient()
    
    # First, set up context with an investigation
    console.print("\n[bold]Setting up context...[/bold]")
    client.chat("Investigate order D12345678", show_intent=False)
    
    # Now classify various queries
    queries = [
        "Why did it fail?",
        "Investigate order ABC123",
        "How does FX pricing work?",
        "Show me the code for spread calculation",
        "Investigate D12345678 again"
    ]
    
    table = Table(title="Query Classification Results", show_header=True)
    table.add_column("Query", style="cyan", width=40)
    table.add_column("Action", style="yellow", width=25)
    table.add_column("Confidence", style="green", width=12)
    
    for query in queries:
        console.print(f"\n[bold]Classifying:[/bold] {query}")
        result = client.classify_query(query)
        classification = result["classification"]
        
        table.add_row(
            query,
            classification["action_type"],
            f"{classification['confidence']:.2f}"
        )
    
    console.print()
    console.print(table)


def example_session_management():
    """
    Example 7: Managing multiple sessions
    """
    console.print(Panel.fit(
        "[bold cyan]Example 7: Session Management[/bold cyan]",
        border_style="cyan"
    ))
    
    # Create multiple clients (separate sessions)
    client1 = ChatbotClient()
    client2 = ChatbotClient()
    
    # Session 1: Investigate order A
    console.print("\n[bold cyan]Session 1:[/bold cyan]")
    console.print("[bold]User:[/bold] Investigate order D11111111")
    response1 = client1.chat("Investigate order D11111111", show_intent=False)
    console.print(f"[dim]Session ID: {client1.session_id}[/dim]")
    
    # Session 2: Investigate order B
    console.print("\n[bold cyan]Session 2:[/bold cyan]")
    console.print("[bold]User:[/bold] Investigate order D22222222")
    response2 = client2.chat("Investigate order D22222222", show_intent=False)
    console.print(f"[dim]Session ID: {client2.session_id}[/dim]")
    
    # List all sessions
    console.print("\n[bold cyan]All Active Sessions:[/bold cyan]")
    sessions = client1.list_all_sessions()
    
    table = Table(show_header=True)
    table.add_column("Session ID", style="cyan")
    table.add_column("Messages", style="white")
    table.add_column("Investigations", style="white")
    table.add_column("Current Order", style="yellow")
    
    for session in sessions["sessions"]:
        table.add_row(
            session["session_id"][:8] + "...",
            str(session["message_count"]),
            str(session["investigation_count"]),
            session.get("current_order", "None")
        )
    
    console.print(table)
    console.print(f"\n[bold]Total Active Sessions:[/bold] {sessions['total']}")


def main():
    """Run all examples"""
    console.print(Panel.fit(
        "[bold white]Intelligent Chatbot API Examples[/bold white]\n"
        "[dim]Demonstrating various usage patterns[/dim]",
        border_style="blue"
    ))
    
    examples = [
        ("1", "Investigation Flow", example_investigation_flow),
        ("2", "Knowledge Queries", example_knowledge_query),
        ("3", "Code Analysis", example_code_analysis),
        ("4", "Re-investigation Prevention", example_reinvestigation_decline),
        ("5", "Order Comparison", example_comparison_flow),
        ("6", "Query Classification", example_query_classification),
        ("7", "Session Management", example_session_management)
    ]
    
    console.print("\n[bold green]Available Examples:[/bold green]")
    for num, name, _ in examples:
        console.print(f"  {num}. {name}")
    console.print("  0. Run all examples")
    console.print("  q. Quit")
    
    while True:
        choice = console.input("\n[bold cyan]Select example to run:[/bold cyan] ").strip()
        
        if choice.lower() == 'q':
            break
        
        if choice == '0':
            for num, name, func in examples:
                console.print(f"\n\n{'='*80}\n")
                try:
                    func()
                except Exception as e:
                    console.print(f"[red]Error running {name}: {str(e)}[/red]")
                console.input("\n[dim]Press Enter to continue...[/dim]")
        else:
            for num, name, func in examples:
                if choice == num:
                    try:
                        func()
                    except Exception as e:
                        console.print(f"[red]Error: {str(e)}[/red]")
                    break


if __name__ == "__main__":
    main()
