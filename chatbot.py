#!/usr/bin/env python3
"""
Chatbot implementation with conversation memory
Allows follow-up questions on investigation results
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, Optional, List
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.graph.workflow import create_supervisor_graph
from src.models.state import AgentState
from src.models.query_parameters import QueryParameters
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from config import settings

console = Console()


class InvestigationChatbot:
    """
    Chatbot that maintains conversation context and can answer follow-up questions
    """
    
    def __init__(self):
        """Initialize chatbot with agent graph and LLM for follow-ups"""
        self.agent = create_supervisor_graph()
        
        # LLM for answering follow-up questions based on context
        self.llm = ChatAnthropic(
            model=settings.agent_model,
            temperature=0.3
        )
        
        # Conversation memory
        self.conversation_history: List[Dict] = []
        self.last_investigation: Optional[AgentState] = None
        self.investigation_context: Dict = {}
        
        console.print("[green]✓[/green] Chatbot initialized!\n")
    
    def create_initial_state(self, query: str) -> AgentState:
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
            # Primary order enrichment fields
            "aaa_order_id": None,
            "enrichment_flow": False,
            "actual_order_id": None,
            # Comparison order enrichment fields
            "comparison_aaa_order_id": None,
            "comparison_enrichment_flow": False,
            "comparison_actual_order_id": None
        }
    
    def is_followup_question(self, query: str) -> bool:
        """
        Determine if this is a follow-up question that can be answered from context
        
        Follow-up indicators:
        - Questions starting with: why, how, what, when, where, explain, tell me more
        - References to "it", "that", "this order", "the error", etc.
        - No new order ID mentioned
        """
        query_lower = query.lower().strip()
        
        # If no previous investigation, it's not a follow-up
        if not self.last_investigation:
            return False
        
        # Follow-up question patterns
        followup_patterns = [
            "why", "how", "what", "when", "where",
            "explain", "tell me", "can you",
            "more details", "more info",
            "what does", "what is", "what about",
            "this order", "that order", "the order",
            "this error", "that error", "the error",
            "it says", "it shows", "it means"
        ]
        
        # New investigation patterns (override follow-up detection)
        new_investigation_patterns = [
            "investigate order",
            "compare order",
            "show me order",
            "get logs for",
            "analyze order",
            "check order"
        ]
        
        # Check if it's a new investigation
        for pattern in new_investigation_patterns:
            if pattern in query_lower:
                return False
        
        # Check if it's a follow-up
        for pattern in followup_patterns:
            if query_lower.startswith(pattern) or pattern in query_lower:
                return True
        
        return False
    
    def answer_followup(self, query: str) -> str:
        """
        Answer follow-up question using previous investigation context
        """
        if not self.last_investigation:
            return "I don't have any previous investigation context. Please start with a new investigation."
        
        # Build context from last investigation
        context_parts = []
        
        # Add basic info
        params = self.last_investigation.get("parameters")
        if params:
            context_parts.append(f"Previous Investigation:")
            context_parts.append(f"- Intent: {params.intent}")
            context_parts.append(f"- Order ID: {params.order_id or 'N/A'}")
            context_parts.append(f"- Date: {params.date or 'N/A'}")
        
        # Add findings from each agent
        findings = self.last_investigation.get("findings", {})
        if findings:
            context_parts.append("\nAgent Findings:")
            for agent_name, agent_data in findings.items():
                if isinstance(agent_data, list):
                    # Multiple calls
                    for idx, call_data in enumerate(agent_data, 1):
                        summary = call_data.get("summary", "")
                        analysis = call_data.get("analysis", "")
                        context_parts.append(f"\n{agent_name} (Call #{idx}):")
                        if summary:
                            context_parts.append(f"  Summary: {summary}")
                        if analysis:
                            context_parts.append(f"  Analysis: {analysis[:500]}")
                elif isinstance(agent_data, dict):
                    # Single call
                    summary = agent_data.get("summary", "")
                    analysis = agent_data.get("analysis", "")
                    context_parts.append(f"\n{agent_name}:")
                    if summary:
                        context_parts.append(f"  Summary: {summary}")
                    if analysis:
                        context_parts.append(f"  Analysis: {analysis[:500]}")
        
        # Add final answer
        final_answer = self.last_investigation.get("final_answer", "")
        if final_answer:
            context_parts.append(f"\nPrevious Answer:\n{final_answer[:1000]}")
        
        context = "\n".join(context_parts)
        
        # Create prompt for LLM
        prompt = f"""You are an expert financial trading analyst helping answer follow-up questions about a previous investigation.

{context}

User's Follow-up Question: {query}

Please answer the user's question based on the investigation context above. If the information needed to answer is not in the context, say so clearly. Be concise but thorough.

Answer:"""
        
        messages = [
            SystemMessage(content="You are a helpful financial trading analyst assistant."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            return f"Error answering follow-up question: {str(e)}"
    
    def run_investigation(self, query: str) -> str:
        """
        Run a full investigation using the agent workflow
        """
        console.print(f"\n[cyan]Running investigation...[/cyan]\n")
        
        state = self.create_initial_state(query)
        result = self.agent.invoke(state)
        
        # Store investigation results
        self.last_investigation = result
        
        # Extract key context for quick access
        params = result.get("parameters")
        if params:
            self.investigation_context = {
                "order_id": params.order_id,
                "date": params.date,
                "intent": params.intent,
                "timestamp": datetime.now().isoformat()
            }
        
        # Add to conversation history
        self.conversation_history.append({
            "type": "investigation",
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "result": result
        })
        
        return result.get("final_answer", "Investigation completed but no answer generated.")
    
    def chat(self, query: str) -> str:
        """
        Main chat method - routes to investigation or follow-up
        """
        # Add user message to history
        self.conversation_history.append({
            "type": "user_query",
            "query": query,
            "timestamp": datetime.now().isoformat()
        })
        
        # Determine if this is a follow-up or new investigation
        if self.is_followup_question(query):
            console.print("[yellow]⚡ Answering from previous context...[/yellow]\n")
            answer = self.answer_followup(query)
            response_type = "followup"
        else:
            console.print("[cyan]🔍 Starting new investigation...[/cyan]\n")
            answer = self.run_investigation(query)
            response_type = "investigation"
        
        # Add response to history
        self.conversation_history.append({
            "type": f"{response_type}_response",
            "answer": answer,
            "timestamp": datetime.now().isoformat()
        })
        
        return answer
    
    def show_context(self):
        """Display current investigation context"""
        if not self.investigation_context:
            console.print("[yellow]No investigation context available[/yellow]")
            return
        
        console.print("\n[bold cyan]Current Context:[/bold cyan]")
        for key, value in self.investigation_context.items():
            console.print(f"  {key}: {value}")
        console.print()
    
    def clear_context(self):
        """Clear investigation context"""
        self.last_investigation = None
        self.investigation_context = {}
        console.print("[green]✓[/green] Context cleared\n")


def main():
    """Run chatbot in interactive mode"""
    console.print(Panel.fit(
        "[bold cyan]Financial Trading Investigation Chatbot[/bold cyan]\n"
        "[dim]Ask questions about orders, then follow up for more details[/dim]",
        border_style="cyan"
    ))
    
    chatbot = InvestigationChatbot()
    
    console.print("\n[bold green]Commands:[/bold green]")
    console.print("  [cyan]exit/quit[/cyan] - Exit chatbot")
    console.print("  [cyan]clear[/cyan] - Clear context and start fresh")
    console.print("  [cyan]context[/cyan] - Show current investigation context")
    console.print("  [cyan]help[/cyan] - Show example queries\n")
    
    example_flow = """
[bold]Example Conversation:[/bold]
  You: Investigate order D12345678
  Bot: [Runs full investigation]
  
  You: Why did it fail?
  Bot: [Answers from context - no new investigation]
  
  You: What was the error code?
  Bot: [Answers from context]
  
  You: Investigate order ABC123
  Bot: [Runs NEW investigation]
"""
    
    while True:
        try:
            query = console.input("\n[bold cyan]You>[/bold cyan] ")
            
            if not query.strip():
                continue
            
            query_lower = query.lower().strip()
            
            # Handle commands
            if query_lower in ['exit', 'quit', 'q']:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            
            if query_lower == 'clear':
                chatbot.clear_context()
                continue
            
            if query_lower == 'context':
                chatbot.show_context()
                continue
            
            if query_lower == 'help':
                console.print(example_flow)
                continue
            
            # Process query
            start_time = datetime.now()
            answer = chatbot.chat(query)
            duration = (datetime.now() - start_time).total_seconds()
            
            # Display answer
            console.print(f"\n[bold green]Bot>[/bold green]")
            md = Markdown(answer)
            console.print(md)
            console.print(f"\n[dim]({duration:.2f}s)[/dim]")
            
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error: {str(e)}[/red]")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
