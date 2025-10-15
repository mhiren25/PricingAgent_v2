"""
Order Enricher Agent - Processes D-prefixed order IDs
Extends BaseAgent for consistency with other agents
"""

from src.agents.base_agent import BaseAgent
from typing import Dict, Any


class OrderEnricherAgent(BaseAgent):
    """
    Agent responsible for enriching order IDs that start with 'D' and have 9 characters.
    Removes dots and prepares the ID for DB lookup to get the actual order ID.
    """
    
    def __init__(self):
        super().__init__(
            name="Order_Enricher_Agent",
            system_prompt="""You are the **Order ID Enricher** specializing in:
- Processing D-prefixed order identifiers
- Normalizing order ID format (removing dots)
- Validating order ID structure
- Preparing orders for database lookup

Your role is to transform D-prefixed order IDs into a clean format for database queries.""",
            use_cheap_model=True  # Simple task, use cheaper model
        )
    
    def clean_order_id(self, order_id: str) -> str:
        """
        Remove dots from order ID
        
        Args:
            order_id: Order ID with potential dots (e.g., "D12.345.678")
            
        Returns:
            Cleaned order ID (e.g., "D12345678")
        """
        return order_id.replace(".", "")
    
    def validate_order_format(self, order_id: str) -> tuple[bool, str]:
        """
        Validate that order ID matches D-prefix format with 9 characters
        
        Args:
            order_id: Cleaned order ID
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not order_id:
            return False, "Order ID is empty"
        
        if not order_id.startswith("D"):
            return False, f"Order ID must start with 'D', got: {order_id[0]}"
        
        if len(order_id) != 9:
            return False, f"Order ID must be 9 characters, got: {len(order_id)}"
        
        return True, ""
    
    def _execute_tool(self, context: Dict, state: Dict) -> Dict[str, Any]:
        """
        Process order ID enrichment
        
        Args:
            context: Investigation context (includes date)
            state: Current agent state
            
        Returns:
            Dict with enrichment results
        """
        current_inv = state.get("current_investigation", "primary")
        params = state.get("parameters")
        
        # Determine which order ID and date to process
        if current_inv == "comparison":
            order_id = params.comparison_order_id if params and hasattr(params, 'comparison_order_id') else None
            date = params.comparison_date if params and hasattr(params, 'comparison_date') else None
        else:
            order_id = params.order_id if params and hasattr(params, 'order_id') else None
            date = params.date if params and hasattr(params, 'date') else None
        
        prefix = context.get("prefix", "")
        
        if not order_id:
            return {
                "raw_data": f"{prefix} ⚠️ No order ID provided for enrichment",
                "summary": "Error: No order ID provided",
                "error": "No order ID provided for enrichment"
            }
        
        # Store original order ID
        original_order_id = order_id
        
        # Remove dots from order ID
        clean_order_id = self.clean_order_id(order_id)
        
        # Validate the order ID format
        is_valid, error_msg = self.validate_order_format(clean_order_id)
        
        if not is_valid:
            return {
                "raw_data": f"""{prefix} ⚠️ **Order ID Validation Failed**

**Original Order ID:** `{original_order_id}`
**Cleaned Order ID:** `{clean_order_id}`
**Error:** {error_msg}

Expected format: D-prefix with 9 characters total (e.g., D12345678 or D12.345.678)""",
                "summary": f"Validation failed: {error_msg}",
                "error": error_msg,
                "original_order_id": original_order_id
            }
        
        # Store the cleaned order ID in appropriate state field based on phase
        # IMPORTANT: Don't return full state, only return the updates needed
        
        # Date info for display
        date_info = f"\n**Date:** `{date}`" if date else ""
        
        result = {
            "summary": f"Enriched {original_order_id} → {clean_order_id}",
            "original_order_id": original_order_id,
            "cleaned_order_id": clean_order_id,
            "date": date,
            "investigation_phase": current_inv,
            "enrichment_ready": True,
            "raw_data": f"""{prefix} 🔧 **Order ID Enrichment Prepared**

**Original Order ID:** `{original_order_id}`
**Cleaned Order ID:** `{clean_order_id}`{date_info}
**Status:** ✅ Ready for database lookup

**Next Step:** Database Agent will lookup actual Order ID using `{clean_order_id}`

---
*Investigation Phase:* {current_inv.upper()}"""
        }
        
        # Update state fields based on phase - modify state directly, don't return user_query
        if current_inv == "comparison":
            state["comparison_aaa_order_id"] = clean_order_id
            state["comparison_enrichment_flow"] = True
            print(f"[ORDER_ENRICHER] Comparison: comparison_aaa_order_id={clean_order_id}, comparison_enrichment_flow=True")
        else:
            state["aaa_order_id"] = clean_order_id
            state["enrichment_flow"] = True
            print(f"[ORDER_ENRICHER] Primary: aaa_order_id={clean_order_id}, enrichment_flow=True")
        
        return result
