"""
Supervisor Agent - Orchestrator (Updated with Order Enricher and Summarization Agent)
"""

from src.agents.base_agent import BaseAgent
from src.agents.vector_db_agent import VectorDBAgent
from src.agents.splunk_agent import SplunkAgent
from src.agents.database_agent import DatabaseAgent
from src.agents.debug_api_agent import DebugAPIAgent
from src.agents.monitoring_agent import MonitoringAgent
from src.agents.code_agent import CodeAgent
from src.agents.comparison_agent import ComparisonAgent
from src.agents.summarization_agent import SummarizationAgent
from src.agents.order_enricher_agent import OrderEnricherAgent  # NEW!
from src.models.query_parameters import QueryParameters
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from typing import Dict, Any
from config import settings


class SupervisorAgent:
    """Orchestrates specialist agents and synthesizes findings"""
    
    def __init__(self):
        self.name = "Supervisor"
        self.llm = ChatAnthropic(
            model=settings.supervisor_model,
            temperature=0
        ).with_structured_output(QueryParameters)
        
        # Initialize all specialist agents (including Order Enricher and Summarization)
        self.agents = {
            "VectorDB_Agent": VectorDBAgent(),
            "Splunk_Agent": SplunkAgent(),
            "Database_Agent": DatabaseAgent(),
            "DebugAPI_Agent": DebugAPIAgent(),
            "Monitoring_Agent": MonitoringAgent(),
            "Code_Agent": CodeAgent(),
            "Comparison_Agent": ComparisonAgent(),
            "Order_Enricher_Agent": OrderEnricherAgent(),  # NEW!
            "Summarization_Agent": SummarizationAgent()
        }
    
    def analyze_query(self, state: Dict) -> Dict:
        """Analyze query with structured output - handles date normalization"""
        
        analysis_prompt = f"""Analyze this financial trading query:

**User Query:** {state['user_query']}

**Instructions:**
- Determine intent (Knowledge/Data/Debug/Investigation/Monitoring/CodeAnalysis/Comparison)
- Extract order IDs and dates ONLY if present and relevant
- For Knowledge queries (like "How does pricing work?"), NO order_id needed
- For Data queries without specific order (like "Show system logs"), NO order_id needed
- Only extract order_id if user explicitly mentions an order to investigate
- Extract dates in ANY format mentioned (will be normalized automatically)
- If no date is mentioned, leave empty (current date will be used)

**Date Examples:**
- "2025-10-12", "12-10-2025", "10/12/2025" → All valid formats
- "today", "yesterday" → Natural language
- No date mentioned → Will use current date

**Query Examples:**
- "How does GOLD tier pricing work?" → intent=Knowledge, order_id="", date=""
- "Show system health" → intent=Monitoring, order_id="", date=""
- "Investigate order ABC123" → intent=Investigation, order_id="ABC123", date="" (current date will be used)
- "Investigate order ABC123 on 2025-10-12" → intent=Investigation, order_id="ABC123", date="2025-10-12"
- "Compare order ABC123 with DEF456" → intent=Comparison, order_id="ABC123", comparison_order_id="DEF456", dates="" (current date for both)
- "Compare order ABC123 from yesterday with DEF456 from today" → Extract both dates

Provide structured output."""
        
        try:
            params: QueryParameters = self.llm.invoke(analysis_prompt)
            
            # Ensure dates are properly set
            params.ensure_dates_set()
            
            # Format date display
            date_info = ""
            if params.date:
                date_info = f"\nDate: {params.date}"
            
            comparison_info = ""
            if params.intent == "Comparison":
                comparison_info = f"\nComparison Order: {params.comparison_order_id or 'N/A'}"
                if params.comparison_date:
                    comparison_info += f"\nComparison Date: {params.comparison_date}"
            
            ai_message = AIMessage(
                content=f"""**[Supervisor Analysis]**
Intent: {params.intent}
Order ID: {params.order_id or 'Not required'}{date_info}{comparison_info}
Reasoning: {params.reasoning}""",
                name=self.name
            )
            
            # IMPORTANT: Only return updates, never return user_query
            return {
                "parameters": params,
                "messages": [ai_message]
            }
            
        except Exception as e:
            # Fallback - create parameters with empty order_id and current date
            from src.utils.date_handler import DateHandler
            fallback_params = QueryParameters(
                intent="Knowledge",
                date=DateHandler.get_current_date(),
                reasoning=f"Fallback due to error: {e}"
            )
            
            # IMPORTANT: Only return updates
            return {
                "parameters": fallback_params,
                "messages": []
            }
    
    def synthesize_findings(self, state: Dict) -> Dict:
        """
        Synthesize final answer - uses detailed summary from Summarization Agent
        
        The Summarization Agent now uses LLM to create comprehensive summaries,
        so we just extract and display its output
        """
        # Get the detailed summary from Summarization Agent
        summarization_data = state.get("findings", {}).get("Summarization_Agent", {})
        
        if summarization_data and "full_summary" in summarization_data:
            # Use the detailed LLM-generated summary
            final_answer = summarization_data["full_summary"]
        elif summarization_data and "raw_data" in summarization_data:
            # Fallback to raw_data if full_summary not available
            final_answer = summarization_data["raw_data"]
        else:
            # Final fallback to simple synthesis if Summarization Agent didn't run
            final_answer = self._simple_synthesis(state)
        
        state["final_answer"] = final_answer
        
        # Create a more prominent final answer display
        divider = "=" * 80
        state["messages"].append(AIMessage(
            content=f"\n{divider}\n{'FINAL INVESTIGATION REPORT'.center(80)}\n{divider}\n\n{final_answer}\n\n{divider}",
            name=self.name
        ))
        
        return state
    
    def _simple_synthesis(self, state: Dict) -> str:
        """Simple synthesis fallback"""
        findings = state.get("findings", {})
        lines = []
        for agent_name, data in findings.items():
            if isinstance(data, dict):
                summary = data.get("summary", data.get("analysis", ""))
                lines.append(f"**{agent_name}:** {summary}")
        return "\n\n".join(lines) if lines else "No findings available"
