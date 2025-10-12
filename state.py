"""
Agent State Definition - Updated with Order Enrichment support
"""

from typing import TypedDict, Annotated, Sequence, Any, Optional
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """Shared state across all agents"""
    
    # Core messaging and query
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_query: str
    parameters: Any  # QueryParameters object containing intent, order_id, etc.
    
    # Investigation tracking
    investigation_step: int
    current_investigation: str  # "primary" or "comparison"
    sender: str  # Last agent that executed
    
    # Findings storage
    findings: dict  # Findings from each agent indexed by agent name
    comparison_findings: dict  # Specific comparison analysis results
    
    # Order enrichment fields (NEW)
    aaa_order_id: Optional[str]  # Cleaned D-prefixed order ID for DB lookup (None if not applicable)
    enrichment_flow: Optional[bool]  # Flag indicating if this is an enrichment workflow
    actual_order_id: Optional[str]  # Actual order ID retrieved from DB after enrichment
    
    # Output
    final_answer: str  # Synthesized final response
    
    # Error handling
    error_log: list[str]  # List of errors encountered during workflow
