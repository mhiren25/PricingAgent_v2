"""
Splunk Agent - Log Analysis & Forensics Expert
Handles: Log retrieval, order tracking, error analysis
Supports order enrichment flow with actual_order_id
"""

from src.agents.base_agent import BaseAgent
from typing import Dict, Any


class SplunkAgent(BaseAgent):
    """
    Log Analysis & Forensics Expert
    
    Responsibilities:
    - Search Splunk logs for order processing
    - Analyze XML messages
    - Track order flow through system
    - Identify errors and anomalies
    - Support enriched order IDs
    
    Note: order_id and date are OPTIONAL - can search system-wide logs
    """
    
    def __init__(self):
        super().__init__(
            name="Splunk_Agent",
            system_prompt="""You are the **Log Analysis Expert** specializing in:
- Splunk log queries and analysis
- Order processing flow tracking
- Error pattern detection
- XML message parsing and interpretation

Analyze logs thoroughly and identify root causes of issues."""
        )
    
    def search_logs(self, order_id: str = "", date: str = "") -> Dict[str, Any]:
        """
        Search Splunk for logs. Can search for specific order or system-wide.
        
        Args:
            order_id: Order identifier (optional)
            date: Date in YYYY-MM-DD format (optional)
            
        Returns:
            Dict with log entries, analysis, and logs_found flag
        """
        # TODO: Replace with actual Splunk API
        
        if order_id and date:
            # Specific order query
            query = f"index=trading sourcetype=pricing order_id={order_id} date={date}"
            context = f"for order {order_id}"
            logs_found = True  # Simulate logs found
        elif order_id:
            # Order-specific query without date
            query = f"index=trading sourcetype=pricing order_id={order_id}"
            context = f"for order {order_id}"
            logs_found = True  # Simulate logs found
        elif date:
            # Date-specific query
            query = f"index=trading sourcetype=pricing date={date}"
            context = f"for date {date}"
            logs_found = True
        else:
            # System-wide query (recent logs)
            query = "index=trading sourcetype=pricing earliest=-1h"
            context = "system-wide (last 1 hour)"
            logs_found = True
        
        # Simulate finding logs (in production, check actual result count)
        log_content = f"""**Splunk Query Results** {context}

Query: {query}

📋 **Log Entries Found: {"15" if order_id else "125"}**

**Key Events:**
1. [2025-01-15 10:23:45] {"Order received - Order ID: " + order_id if order_id else "System processing 125 orders"}
2. [2025-01-15 10:23:46] Pricing calculation initiated
3. [2025-01-15 10:23:47] Client tier: GOLD, Instrument: EURUSD
4. [2025-01-15 10:23:48] Base price: 1.0850, Spread: 0.0002
5. [2025-01-15 10:23:49] Final price calculated: 1.0852

{f'''**XML Request:**
<PricingRequest>
  <OrderId>{order_id}</OrderId>
  <Client>ABC_Corp</Client>
  <Instrument>EURUSD</Instrument>
  <Quantity>1000000</Quantity>
</PricingRequest>

**XML Response:**
<PricingResponse>
  <FinalPrice>1.0852</FinalPrice>
  <Timestamp>2025-01-15T10:23:49Z</Timestamp>
  <Status>SUCCESS</Status>
</PricingResponse>''' if order_id else '**Summary:** All systems operational. No errors in last hour.'}

**Status:** ✅ {"Order processed successfully" if order_id else "System healthy"}
"""
        
        return {
            "log_content": log_content,
            "logs_found": logs_found,
            "order_id": order_id or "system-wide"
        }
    
    def _execute_tool(self, context: Dict, state: Dict) -> Dict[str, Any]:
        """
        Execute log search and analysis
        
        Supports enrichment flow: uses actual_order_id if available
        
        Args:
            context: Investigation context
            state: Current agent state
            
        Returns:
            Dict with log search results and logs_found flag
        """
        # Determine which order ID to use
        order_id = context.get("order_id", "")
        date = context.get("date", "")
        prefix = context.get("prefix", "")
        
        # IMPORTANT: Check for actual_order_id from enrichment flow
        actual_order_id = state.get("actual_order_id")
        if actual_order_id:
            # Use enriched order ID
            order_id = actual_order_id
            prefix += f" [Using enriched Order ID: {actual_order_id}]"
        
        # Check if order_id is in aaa format (shouldn't happen if enrichment worked)
        if order_id and order_id.startswith("D") and len(order_id.replace(".", "")) == 9:
            # This shouldn't happen if enrichment flow worked correctly
            prefix += " ⚠️ [WARNING: Using AAA format order ID - enrichment may have failed]"
        
        # order_id and date are OPTIONAL
        # Only warn if this is Investigation intent but missing params
        params = state.get("parameters")
        if params and params.intent in ["Investigation", "Data"] and not order_id:
            # For these intents, we might need order_id, but can still search system-wide
            prefix += " [System-wide search]"
        
        # Call search method
        result = self.search_logs(order_id, date)
        
        # Extract results
        log_content = result["log_content"]
        logs_found = result["logs_found"]
        
        return {
            "raw_data": log_content,
            "summary": f"Logs {'found' if logs_found else 'NOT found'}{' for ' + order_id if order_id else ' (system-wide)'}",
            "order_id": order_id or "system-wide",
            "logs_found": logs_found,  # CRITICAL: This flag determines routing
            "prefix": prefix
        }
