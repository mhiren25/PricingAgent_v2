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


def replace_value(left: Any, right: Any) -> Any:
    """Replace value - used for fields that can be updated multiple times"""
    return right


class AgentState(TypedDict):
    """Shared state across all agents"""
    
    # Core messaging and query (DO NOT UPDATE THESE)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_query: str  # NEVER update this field after initialization
    parameters: Any  # QueryParameters object - set once by Supervisor
    
    # Investigation tracking (can be updated multiple times)
    investigation_step: Annotated[int, replace_value]
    current_investigation: Annotated[str, replace_value]  # "primary" or "comparison"
    sender: Annotated[str, replace_value]  # Last agent that executed - CAN BE UPDATED
    
    # Findings storage (merged, not replaced)
    findings: Annotated[dict, update_dict]  # Findings from each agent
    comparison_findings: Annotated[dict, update_dict]  # Comparison findings
    
    # Primary order enrichment fields (can be updated multiple times)
    aaa_order_id: Annotated[Optional[str], replace_value]
    enrichment_flow: Annotated[Optional[bool], replace_value]
    actual_order_id: Annotated[Optional[str], replace_value]
    
    # Comparison order enrichment fields (can be updated multiple times)
    comparison_aaa_order_id: Annotated[Optional[str], replace_value]
    comparison_enrichment_flow: Annotated[Optional[bool], replace_value]
    comparison_actual_order_id: Annotated[Optional[str], replace_value]
    
    # Output (can be updated)
    final_answer: Annotated[str, replace_value]
    
    # Error handling (append, not replace)
    error_log: Annotated[list[str], operator.add]
