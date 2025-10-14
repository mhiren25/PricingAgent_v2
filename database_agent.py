"""
Database Agent - Oracle Database & Configuration Expert
Handles: SQL queries, configuration lookup, trade data retrieval, order enrichment
"""

from src.agents.base_agent import BaseAgent
from langchain_core.tools import tool
from typing import Dict, Any


class DatabaseAgent(BaseAgent):
    """Oracle Database & Configuration Expert"""
    
    def __init__(self):
        super().__init__(
            name="Database_Agent",
            system_prompt="""You are the **Database Expert** specializing in:
- Oracle SQL queries and optimization
- Trade data retrieval
- Configuration lookup (pricing rules, client tiers)
- Data integrity validation
- Order ID enrichment and lookup

Provide precise SQL queries and interpret database results accurately."""
        )
    
    @tool
    def lookup_actual_order_id(self, aaa_order_id: str) -> Dict[str, str]:
        """
        Lookup actual order ID using AAA order ID (D-prefixed)
        
        Args:
            aaa_order_id: D-prefixed order ID (e.g., D12345678)
            
        Returns:
            Dict with actual_order_id and lookup status
        """
        # TODO: Replace with actual Oracle connection
        # Example query: SELECT actual_order_id FROM order_mappings WHERE aaa_order_id = ?
        
        # Simulated lookup - remove D prefix and add ORD prefix
        actual_order_id = f"ORD{aaa_order_id[1:]}"  # D12345678 -> ORD12345678
        
        return {
            "actual_order_id": actual_order_id,
            "aaa_order_id": aaa_order_id,
            "lookup_status": "success"
        }
    
    @tool
    def query_database(self, order_id: str) -> str:
        """
        Query Oracle database for order details.
        
        Args:
            order_id: Order identifier
            
        Returns:
            Database query results with trade details
        """
        # TODO: Replace with actual Oracle connection
        return f"""**Database Query Results**

```sql
SELECT o.order_id, o.client_id, c.tier, o.instrument, 
       o.quantity, o.status, p.base_price, p.spread
FROM orders o
JOIN clients c ON o.client_id = c.client_id
JOIN pricing p ON o.instrument = p.instrument
WHERE o.order_id = '{order_id}';
```

**Results:**
| ORDER_ID | CLIENT_ID | TIER | INSTRUMENT | QUANTITY | STATUS | BASE_PRICE | SPREAD |
|----------|-----------|------|------------|----------|--------|------------|--------|
| {order_id} | CLI_001 | GOLD | EURUSD | 1000000 | COMPLETED | 1.0850 | 0.0002 |

**Client Configuration:**
- Client: ABC Corporation (CLI_001)
- Tier: GOLD (10% discount on spreads)
- Active Since: 2020-03-15
- Credit Limit: $50M

**Pricing Rules Applied:**
- Base pricing: Market rate
- Spread adjustment: -10% (GOLD tier)
- Volume discount: Applied for trades > 500K
"""
    
    def _execute_tool(self, context: Dict, state: Dict) -> Dict[str, Any]:
        """
        Execute database queries - handles both enrichment and normal flow
        Uses separate fields for primary vs comparison orders
        
        Args:
            context: Investigation context
            state: Agent state
            
        Returns:
            Dict with query results
        """
        current_inv = state.get("current_investigation", "primary")
        
        # Get enrichment flags based on current investigation phase
        if current_inv == "comparison":
            enrichment_flow = state.get("comparison_enrichment_flow", False)
            aaa_order_id = state.get("comparison_aaa_order_id")
            print(f"\n[DB_AGENT] COMPARISON - enrichment_flow={enrichment_flow}, aaa_order_id={aaa_order_id}")
        else:
            enrichment_flow = state.get("enrichment_flow", False)
            aaa_order_id = state.get("aaa_order_id")
            print(f"\n[DB_AGENT] PRIMARY - enrichment_flow={enrichment_flow}, aaa_order_id={aaa_order_id}")
        
        if enrichment_flow:
            # ENRICHMENT MODE: Lookup actual order ID
            if not aaa_order_id:
                return {
                    "error": "Missing aaa_order_id in enrichment flow",
                    "summary": "⚠️ AAA Order ID required for enrichment lookup"
                }
            
            print(f"[DB_AGENT] ENRICHMENT MODE: Looking up {aaa_order_id}")
            
            # Lookup actual order ID
            lookup_result = self.lookup_actual_order_id.invoke({"aaa_order_id": aaa_order_id})
            actual_order_id = lookup_result["actual_order_id"]
            
            # Store actual_order_id in appropriate state field
            if current_inv == "comparison":
                state["comparison_actual_order_id"] = actual_order_id
                state["comparison_enrichment_flow"] = False  # Clear flag
                print(f"[DB_AGENT] Enrichment complete: comparison_actual_order_id={actual_order_id}, comparison_enrichment_flow=False")
            else:
                state["actual_order_id"] = actual_order_id
                state["enrichment_flow"] = False  # Clear flag
                print(f"[DB_AGENT] Enrichment complete: actual_order_id={actual_order_id}, enrichment_flow=False")
            
            # DO NOT modify params.order_id directly - causes InvalidUpdateError
            # The context will use actual_order_id from state instead
            
            return {
                "raw_data": f"""**Order ID Enrichment Completed**

🔍 **Lookup Details:**
- AAA Order ID (Input): `{aaa_order_id}`
- Actual Order ID (Found): `{actual_order_id}`
- Investigation Phase: {current_inv.upper()}
- Lookup Status: ✅ Success

**Next Step:** Using `{actual_order_id}` for investigation

---
*Note: This order used D-prefix format and required enrichment to find the actual order ID.*
""",
                "summary": f"Enriched {aaa_order_id} → {actual_order_id}",
                "actual_order_id": actual_order_id,
                "aaa_order_id": aaa_order_id,
                "enrichment_completed": True
            }
        
        else:
            # NORMAL MODE: Query trade data
            order_id = context.get("order_id", "")
            
            # Check if we should use actual_order_id from enrichment
            if not order_id:
                if current_inv == "comparison":
                    order_id = state.get("comparison_actual_order_id", "")
                else:
                    order_id = state.get("actual_order_id", "")
            
            print(f"[DB_AGENT] NORMAL MODE: Querying trade data for {order_id}")
            
            if not order_id:
                return {
                    "error": "Missing order_id",
                    "summary": "⚠️ Order ID required for database lookup"
                }
            
            result = self.query_database.invoke({"order_id": order_id})
            
            return {
                "raw_data": result,
                "summary": f"Database records retrieved for {order_id}",
                "order_id": order_id
            }
