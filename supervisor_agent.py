"""
Supervisor Agent - Orchestrator (Updated with Summarization Agent)
"""

from src.agents.base_agent import BaseAgent
from src.agents.vector_db_agent import VectorDBAgent
from src.agents.splunk_agent import SplunkAgent
from src.agents.database_agent import DatabaseAgent
from src.agents.debug_api_agent import DebugAPIAgent
from src.agents.monitoring_agent import MonitoringAgent
from src.agents.code_agent import CodeAgent
from src.agents.comparison_agent import ComparisonAgent
from src.agents.summarization_agent import SummarizationAgent  # NEW!
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
        
        # Initialize all specialist agents (including Summarization)
        self.agents = {
            "VectorDB_Agent": VectorDBAgent(),
            "Splunk_Agent": SplunkAgent(),
            "Database_Agent": DatabaseAgent(),
            "DebugAPI_Agent": DebugAPIAgent(),
            "Monitoring_Agent": MonitoringAgent(),
            "Code_Agent": CodeAgent(),
            "Comparison_Agent": ComparisonAgent(),
            "Summarization_Agent": SummarizationAgent()  # NEW!
        }
    
    def analyze_query(self, state: Dict) -> Dict:
        """Analyze query with structured output - order_id optional based on intent"""
        
        analysis_prompt = f"""Analyze this financial trading query:

**User Query:** {state['user_query']}

**Instructions:**
- Determine intent (Knowledge/Data/Debug/Investigation/Monitoring/CodeAnalysis/Comparison)
- Extract order IDs and dates ONLY if present and relevant
- For Knowledge queries (like "How does pricing work?"), NO order_id needed
- For Data queries without specific order (like "Show system logs"), NO order_id needed
- Only extract order_id if user explicitly mentions an order to investigate

**Examples:**
- "How does GOLD tier pricing work?" → intent=Knowledge, order_id=""
- "Show system health" → intent=Monitoring, order_id=""
- "Investigate order ABC123" → intent=Investigation, order_id="ABC123"
- "Show logs for order ABC123" → intent=Data, order_id="ABC123"

Provide structured output."""
        
        try:
            params: QueryParameters = self.llm.invoke(analysis_prompt)
            state["parameters"] = params
            
            state["messages"].append(AIMessage(
                content=f"""**[Supervisor Analysis]**
Intent: {params.intent}
Order ID: {params.order_id or 'Not required'}
Comparison Order: {params.comparison_order_id or 'N/A'}
Reasoning: {params.reasoning}""",
                name=self.name
            ))
        except Exception as e:
            # Fallback - create parameters with empty order_id
            state["parameters"] = QueryParameters(
                intent="Knowledge",
                reasoning=f"Fallback due to error: {e}"
            )
        
        return state
    
    def synthesize_findings(self, state: Dict) -> Dict:
        """
        Synthesize final answer - now uses Summarization Agent
        
        Instead of doing synthesis here, we delegate to Summarization Agent
        for better formatting and insights
        """
        # Get the summary from Summarization Agent
        summarization_data = state.get("findings", {}).get("Summarization_Agent", {})
        
        if summarization_data and "raw_data" in summarization_data:
            # Use the formatted summary from Summarization Agent
            final_answer = summarization_data["raw_data"]
        else:
            # Fallback to simple synthesis if Summarization Agent didn't run
            final_answer = self._simple_synthesis(state)
        
        state["final_answer"] = final_answer
        state["messages"].append(AIMessage(
            content=f"\n{'='*80}\n**FINAL ANSWER**\n{'='*80}\n\n{final_answer}",
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
