#!/usr/bin/env python3
"""
Intelligent Chatbot with LLM-based routing
Uses structured output to determine appropriate action for each query
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.graph.workflow import create_supervisor_graph
from src.models.state import AgentState
from src.models.query_parameters import QueryParameters
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

console = Console()


# Structured output models for intelligent routing
class QueryIntent(BaseModel):
    """Structured intent classification for user queries"""
    action_type: Literal[
        "answer_from_context",      # Answer using existing investigation findings
        "new_investigation",         # Start new order investigation
        "call_knowledge_agent",      # Query knowledge base/documentation
        "call_code_agent",           # Analyze code/repository
        "call_debug_api",            # Query debug API directly
        "call_monitoring_agent",     # Check monitoring/metrics
        "clarification_needed",      # Need more info from user
        "decline_reinvestigation"    # User wants re-investigation of same order
    ] = Field(description="The type of action needed to answer the user's query")
    
    confidence: float = Field(
        ge=0.0, 
        le=1.0, 
        description="Confidence level in this classification (0.0 to 1.0)"
    )
    
    reasoning: str = Field(
        description="Brief explanation of why this action was chosen"
    )
    
    requires_context: bool = Field(
        description="Whether this action requires previous investigation context"
    )
    
    extracted_entities: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Extracted entities like order_id, date, code_path, etc."
    )
    
    suggested_response: Optional[str] = Field(
        default=None,
        description="If action is clarification/decline, provide suggested response"
    )


class InvestigationChatbot:
    """
    Intelligent chatbot with LLM-based routing and context awareness
    """
    
    def __init__(self):
        """Initialize chatbot with agent graph and routing LLM"""
        self.agent = create_supervisor_graph()
        
        # Main LLM for follow-up answers
        self.llm = ChatAnthropic(
            model=settings.agent_model,
            temperature=0.3
        )
        
        # Routing LLM with structured output
        self.routing_llm = ChatAnthropic(
            model=settings.agent_model,
            temperature=0.1  # Lower temp for more consistent routing
        ).with_structured_output(QueryIntent)
        
        # Conversation memory
        self.conversation_history: List[Dict] = []
        self.last_investigation: Optional[AgentState] = None
        self.investigation_context: Dict = {}
        
        console.print("[green]✓[/green] Intelligent Chatbot initialized!\n")
    
    def classify_query(self, query: str) -> QueryIntent:
        """
        Use LLM to intelligently classify the user's query and determine action
        """
        # Build context summary
        context_summary = self._build_context_summary()
        
        # Create classification prompt
        system_prompt = """You are an intelligent query router for a financial trading investigation system.

Your job is to analyze user queries and determine the appropriate action:

1. **answer_from_context**: User is asking about findings from a previous investigation
   - Examples: "Why did it fail?", "What was the error?", "Explain the pricing difference"
   - Requires: Previous investigation context must exist

2. **new_investigation**: User wants to investigate a NEW order (different from previous)
   - Examples: "Investigate order D12345678", "Check order ABC123"
   - Creates: Complete new investigation workflow

3. **call_knowledge_agent**: User needs documentation, best practices, or general knowledge
   - Examples: "How does FX pricing work?", "What is a spread?", "Explain order types"
   - Does NOT require: Investigation context

4. **call_code_agent**: User wants code analysis or repository queries
   - Examples: "Show me the pricing algorithm", "Find the spread calculation code"
   - May require: Code path or function name

5. **call_debug_api**: User wants to query debug API for specific data
   - Examples: "Get debug info for order X", "Show me the API response"
   - Requires: Order ID

6. **call_monitoring_agent**: User wants metrics, logs, or monitoring data
   - Examples: "Show me system metrics", "Check error rates", "What's the latency?"
   - May require: Time range

7. **clarification_needed**: Query is ambiguous or missing critical information
   - Examples: "Check the order" (which order?), "Why?" (context unclear)
   - Requires: More details from user

8. **decline_reinvestigation**: User wants to re-run the SAME investigation
   - Examples: "Investigate D12345678 again", "Re-check that order"
   - Should: Politely decline and suggest clearing context first

CRITICAL RULES:
- If there's NO previous investigation context, NEVER choose "answer_from_context"
- If user asks about the SAME order as previous investigation, choose "decline_reinvestigation"
- If user asks about a DIFFERENT order, choose "new_investigation"
- Extract ALL relevant entities (order_id, date, etc.) into extracted_entities
- Be conservative: if unsure, choose "clarification_needed"
"""

        user_prompt = f"""**Current Context:**
{context_summary}

**User Query:** {query}

**Task:** Classify this query and determine the appropriate action."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            intent: QueryIntent = self.routing_llm.invoke(messages)
            
            # Validate intent based on context
            if intent.action_type == "answer_from_context" and not self.last_investigation:
                # Override - can't answer from context if no context exists
                intent.action_type = "clarification_needed"
                intent.reasoning = "No previous investigation context available"
                intent.suggested_response = "I don't have any previous investigation context. Please start with a new investigation or ask a general question."
            
            return intent
            
        except Exception as e:
            console.print(f"[red]Error classifying query: {str(e)}[/red]")
            # Fallback to clarification
            return QueryIntent(
                action_type="clarification_needed",
                confidence=0.0,
                reasoning=f"Classification error: {str(e)}",
                requires_context=False,
                suggested_response="I encountered an error understanding your query. Could you rephrase it?"
            )
    
    def _build_context_summary(self) -> str:
        """Build a concise summary of current investigation context"""
        if not self.investigation_context:
            return "No previous investigation context available."
        
        lines = ["**Previous Investigation Context:**"]
        lines.append(f"- Order ID: {self.investigation_context.get('order_id', 'N/A')}")
        lines.append(f"- Date: {self.investigation_context.get('date', 'N/A')}")
        lines.append(f"- Intent: {self.investigation_context.get('intent', 'N/A')}")
        lines.append(f"- Timestamp: {self.investigation_context.get('timestamp', 'N/A')}")
        
        if self.last_investigation:
            findings = self.last_investigation.get("findings", {})
            if findings:
                lines.append(f"- Available findings from: {', '.join(findings.keys())}")
        
        return "\n".join(lines)
    
    def answer_from_context(self, query: str) -> str:
        """Answer question using previous investigation context"""
        if not self.last_investigation:
            return "I don't have any previous investigation context. Please start with a new investigation."
        
        # Build comprehensive context
        context_parts = []
        
        # Basic info
        params = self.last_investigation.get("parameters")
        if params:
            context_parts.append(f"**Previous Investigation:**")
            context_parts.append(f"- Intent: {params.intent}")
            context_parts.append(f"- Order ID: {params.order_id or 'N/A'}")
            context_parts.append(f"- Date: {params.date or 'N/A'}")
        
        # Agent findings
        findings = self.last_investigation.get("findings", {})
        if findings:
            context_parts.append("\n**Agent Findings:**")
            for agent_name, agent_data in findings.items():
                if isinstance(agent_data, list):
                    for idx, call_data in enumerate(agent_data, 1):
                        summary = call_data.get("summary", "")
                        analysis = call_data.get("analysis", "")
                        context_parts.append(f"\n{agent_name} (Call #{idx}):")
                        if summary:
                            context_parts.append(f"  Summary: {summary}")
                        if analysis:
                            context_parts.append(f"  Analysis: {analysis[:800]}")
                elif isinstance(agent_data, dict):
                    summary = agent_data.get("summary", "")
                    analysis = agent_data.get("analysis", "")
                    context_parts.append(f"\n{agent_name}:")
                    if summary:
                        context_parts.append(f"  Summary: {summary}")
                    if analysis:
                        context_parts.append(f"  Analysis: {analysis[:800]}")
        
        # Comparison findings if available
        comparison_findings = self.last_investigation.get("comparison_findings", {})
        if comparison_findings:
            context_parts.append("\n**Comparison Order Findings:**")
            for agent_name, agent_data in comparison_findings.items():
                if isinstance(agent_data, dict):
                    summary = agent_data.get("summary", "")
                    if summary:
                        context_parts.append(f"{agent_name}: {summary}")
        
        # Final answer
        final_answer = self.last_investigation.get("final_answer", "")
        if final_answer:
            context_parts.append(f"\n**Previous Summary:**\n{final_answer[:1500]}")
        
        context = "\n".join(context_parts)
        
        # Create answer prompt
        prompt = f"""You are a financial trading analyst answering follow-up questions about a previous investigation.

{context}

**User's Question:** {query}

**Instructions:**
- Answer based ONLY on the investigation context above
- Be specific and cite relevant findings
- If the information isn't in the context, say so clearly
- Be concise but thorough
- Use bullet points for clarity when appropriate

**Answer:**"""
        
        messages = [
            SystemMessage(content="You are a helpful financial trading analyst."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            return f"Error generating answer: {str(e)}"
    
    def run_new_investigation(self, query: str) -> str:
        """Run a full investigation workflow"""
        console.print(f"\n[cyan]🔍 Starting new investigation...[/cyan]\n")
        
        state = self.create_initial_state(query)
        result = self.agent.invoke(state)
        
        # Store investigation results
        self.last_investigation = result
        
        # Extract context
        params = result.get("parameters")
        if params:
            self.investigation_context = {
                "order_id": params.order_id,
                "date": params.date,
                "intent": params.intent,
                "timestamp": datetime.now().isoformat()
            }
        
        # Add to history
        self.conversation_history.append({
            "type": "investigation",
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "result": result
        })
        
        return result.get("final_answer", "Investigation completed but no answer generated.")
    
    def call_single_agent(self, agent_type: str, query: str, extracted_entities: Dict) -> str:
        """
        Call a specific agent without full investigation workflow
        """
        console.print(f"\n[yellow]⚡ Calling {agent_type}...[/yellow]\n")
        
        # Map action types to intents
        intent_map = {
            "call_knowledge_agent": "Knowledge",
            "call_code_agent": "CodeAnalysis",
            "call_debug_api": "Data",
            "call_monitoring_agent": "Monitoring"
        }
        
        intent = intent_map.get(agent_type, "Data")
        
        # Create simplified state for single agent call
        state = self.create_initial_state(query)
        
        # Update parameters with extracted entities
        if state.get("parameters"):
            params = state["parameters"]
            for key, value in extracted_entities.items():
                if hasattr(params, key) and value:
                    setattr(params, key, value)
            params.intent = intent
        
        try:
            result = self.agent.invoke(state)
            
            # Store partial context (don't overwrite full investigation)
            self.conversation_history.append({
                "type": "single_agent_call",
                "agent": agent_type,
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "result": result
            })
            
            return result.get("final_answer", "Agent call completed.")
            
        except Exception as e:
            return f"Error calling {agent_type}: {str(e)}"
    
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
            "aaa_order_id": None,
            "enrichment_flow": False,
            "actual_order_id": None,
            "comparison_aaa_order_id": None,
            "comparison_enrichment_flow": False,
            "comparison_actual_order_id": None
        }
    
    def chat(self, query: str) -> str:
        """
        Main chat method with intelligent routing
        """
        # Add to history
        self.conversation_history.append({
            "type": "user_query",
            "query": query,
            "timestamp": datetime.now().isoformat()
        })
        
        # Classify query using LLM
        intent = self.classify_query(query)
        
        # Log classification
        console.print(f"\n[dim]Intent: {intent.action_type} (confidence: {intent.confidence:.2f})[/dim]")
        console.print(f"[dim]Reasoning: {intent.reasoning}[/dim]\n")
        
        # Route based on classification
        if intent.action_type == "answer_from_context":
            console.print("[yellow]💬 Answering from previous context...[/yellow]\n")
            answer = self.answer_from_context(query)
            response_type = "context_answer"
        
        elif intent.action_type == "new_investigation":
            answer = self.run_new_investigation(query)
            response_type = "investigation"
        
        elif intent.action_type in [
            "call_knowledge_agent",
            "call_code_agent", 
            "call_debug_api",
            "call_monitoring_agent"
        ]:
            answer = self.call_single_agent(
                intent.action_type, 
                query, 
                intent.extracted_entities
            )
            response_type = "single_agent"
        
        elif intent.action_type == "decline_reinvestigation":
            answer = intent.suggested_response or (
                "I see you want to re-investigate the same order. To ensure fresh results, "
                "please use the `clear` command to reset the context, then submit your investigation request again."
            )
            response_type = "decline"
        
        elif intent.action_type == "clarification_needed":
            answer = intent.suggested_response or (
                "I need more information to help you. Could you please provide more details about what you'd like to know?"
            )
            response_type = "clarification"
        
        else:
            answer = "I'm not sure how to handle that request. Could you rephrase it?"
            response_type = "unknown"
        
        # Add response to history
        self.conversation_history.append({
            "type": f"{response_type}_response",
            "answer": answer,
            "intent_classification": intent.model_dump(),
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
    
    def show_history(self, limit: int = 5):
        """Show recent conversation history"""
        if not self.conversation_history:
            console.print("[yellow]No conversation history[/yellow]")
            return
        
        console.print(f"\n[bold cyan]Recent History (last {limit}):[/bold cyan]")
        for entry in self.conversation_history[-limit:]:
            type_emoji = {
                "user_query": "👤",
                "investigation": "🔍",
                "context_answer": "💬",
                "single_agent": "⚡",
                "clarification": "❓",
                "decline": "🚫"
            }.get(entry["type"], "📝")
            
            console.print(f"{type_emoji} [{entry['timestamp']}] {entry['type']}")
            if entry.get("query"):
                console.print(f"   Query: {entry['query'][:100]}")
        console.print()


def main():
    """Run chatbot in interactive mode"""
    console.print(Panel.fit(
        "[bold cyan]🤖 Intelligent Financial Trading Investigation Chatbot[/bold cyan]\n"
        "[dim]Powered by LLM-based intelligent routing[/dim]",
        border_style="cyan"
    ))
    
    chatbot = InvestigationChatbot()
    
    console.print("\n[bold green]Commands:[/bold green]")
    console.print("  [cyan]exit/quit[/cyan] - Exit chatbot")
    console.print("  [cyan]clear[/cyan] - Clear investigation context")
    console.print("  [cyan]context[/cyan] - Show current investigation context")
    console.print("  [cyan]history[/cyan] - Show recent conversation history")
    console.print("  [cyan]help[/cyan] - Show example queries\n")
    
    example_flow = """
[bold]Example Conversations:[/bold]

[bold cyan]1. Investigation with Follow-ups:[/bold cyan]
  You: Investigate order D12345678
  Bot: [Runs full investigation]
  
  You: Why did it fail?
  Bot: [Answers from context - no new investigation]
  
  You: What was the spread?
  Bot: [Answers from context]

[bold cyan]2. Knowledge Query:[/bold cyan]
  You: How does FX pricing work?
  Bot: [Calls Knowledge Agent - no investigation needed]

[bold cyan]3. Code Analysis:[/bold cyan]
  You: Show me the spread calculation code
  Bot: [Calls Code Agent]

[bold cyan]4. Re-investigation Request:[/bold cyan]
  You: Investigate D12345678 again
  Bot: Please clear context first to re-investigate

[bold cyan]5. New Investigation:[/bold cyan]
  You: Check order ABC123
  Bot: [Starts NEW investigation]
"""
    
    while True:
        try:
            query = console.input("\n[bold cyan]You>[/bold cyan] ")
            
            if not query.strip():
                continue
            
            query_lower = query.lower().strip()
            
            # Handle commands
            if query_lower in ['exit', 'quit', 'q']:
                console.print("\n[yellow]Goodbye! 👋[/yellow]")
                break
            
            if query_lower == 'clear':
                chatbot.clear_context()
                continue
            
            if query_lower == 'context':
                chatbot.show_context()
                continue
            
            if query_lower == 'history':
                chatbot.show_history()
                continue
            
            if query_lower == 'help':
                console.print(example_flow)
                continue
            
            # Process query with intelligent routing
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
