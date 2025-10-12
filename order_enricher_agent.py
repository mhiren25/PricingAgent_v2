"""
Order Enricher Agent - Processes D-prefixed order IDs
Removes dots and stores as aaa_order_id for DB lookup
"""

from src.models.state import AgentState


class OrderEnricherAgent:
    """
    Agent responsible for enriching order IDs that start with 'D' and have 9 characters.
    Removes dots and prepares the ID for DB lookup to get the actual order ID.
    """
    
    def __init__(self):
        self.name = "Order_Enricher_Agent"
    
    def execute(self, state: AgentState) -> dict:
        """
        Process order ID enrichment
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with aaa_order_id and enrichment flag
        """
        params = state.get("parameters")
        current_inv = state.get("current_investigation", "primary")
        
        # Determine which order ID to process
        if current_inv == "comparison":
            order_id = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
        else:
            order_id = params.order_id if hasattr(params, 'order_id') else None
        
        if not order_id:
            return {
                "findings": {
                    self.name: {
                        "status": "error",
                        "message": "No order ID provided for enrichment"
                    }
                }
            }
        
        # Remove dots from order ID
        clean_order_id = order_id.replace(".", "")
        
        # Validate the order ID format
        if not (clean_order_id.startswith("D") and len(clean_order_id) == 9):
            return {
                "findings": {
                    self.name: {
                        "status": "error",
                        "message": f"Invalid order ID format: {order_id}. Expected D-prefix with 9 characters (after removing dots)",
                        "original_order_id": order_id
                    }
                }
            }
        
        # Store the cleaned order ID as aaa_order_id
        result = {
            "aaa_order_id": clean_order_id,
            "enrichment_flow": True,  # Flag to indicate this is an enrichment flow
            "findings": {
                self.name: {
                    "status": "success",
                    "original_order_id": order_id,
                    "cleaned_order_id": clean_order_id,
                    "message": f"Order ID enriched: {order_id} -> {clean_order_id}. DB Agent will fetch actual order ID.",
                    "investigation_phase": current_inv
                }
            }
        }
        
        return result
    
    def get_info(self) -> dict:
        """Return agent information"""
        return {
            "name": self.name,
            "description": "Enriches D-prefixed order IDs by removing dots and preparing for DB lookup",
            "capabilities": [
                "Remove dots from order IDs",
                "Validate D-prefix format (9 characters)",
                "Store as aaa_order_id for DB Agent lookup",
                "Support both primary and comparison order flows"
            ]
        }
