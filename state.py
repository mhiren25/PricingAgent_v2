"""
Agent State Definition - Updated with Order Enrichment support
Fixed to prevent InvalidUpdateError
"""

from typing import TypedDict, Annotated, Sequence, Any, Optional
from langchain_core.messages import BaseMessage
import operator


def update_dict(left: dict, right: dict) -> dict:
    """Merge two dictionaries without overwriting"""
    result = {**left}
    result.update(right)
    return result


class AgentState(TypedDict):
    """Shared state across all agents"""
    
    # Core messaging and query (DO NOT UPDATE THESE)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_query: str  # NEVER update this field after initialization
    parameters: Any  # QueryParameters object - set once by Supervisor
    
    # Investigation tracking (can be updated)
    investigation_step: int
    current_investigation: str  # "primary" or "comparison"
    sender: str  # Last agent that executed
    
    # Findings storage (merged, not replaced)
    findings: Annotated[dict, update_dict]  # Findings from each agent
    comparison_findings: Annotated[dict, update_dict]  # Comparison findings
    
    # Primary order enrichment fields (can be updated)
    aaa_order_id: Optional[str]
    enrichment_flow: Optional[bool]
    actual_order_id: Optional[str]
    
    # Comparison order enrichment fields (can be updated)
    comparison_aaa_order_id: Optional[str]
    comparison_enrichment_flow: Optional[bool]
    comparison_actual_order_id: Optional[str]
    
    # Output
    final_answer: str
    
    # Error handling (append, not replace)
    error_log: Annotated[list[str], operator.add]
