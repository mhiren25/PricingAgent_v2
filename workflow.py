"""
Main workflow construction - includes Order Enricher and Summarization Agent
Fixed flow with Order ID enrichment for D-prefixed orders
"""

from langgraph.graph import StateGraph, END
from src.agents.supervisor_agent import SupervisorAgent
from src.models.state import AgentState


def create_supervisor_graph():
    """Create optimized multi-agent workflow with order enrichment and conditional routing"""
    
    supervisor = SupervisorAgent()
    workflow = StateGraph(AgentState)
    
    # Add supervisor and synthesis nodes
    workflow.add_node("supervisor", lambda s: supervisor.analyze_query(s))
    workflow.add_node("synthesize", lambda s: supervisor.synthesize_findings(s))
    
    # Add transition nodes for comparison flow
    def switch_to_comparison(state):
        """Transition node: Switch from primary to comparison investigation"""
        print("[TRANSITION] Switching to comparison phase")
        # Only return fields that need updating - NEVER include user_query
        return {
            "current_investigation": "comparison",
            "investigation_step": 0,
            "messages": state["messages"]  # Pass through
        }
    
    def switch_to_comparison_enricher(state):
        """Transition node: Switch to comparison and prepare for enrichment"""
        print("[TRANSITION] Switching to comparison phase (with enrichment)")
        # Only return fields that need updating - NEVER include user_query
        return {
            "current_investigation": "comparison",
            "investigation_step": 0,
            "messages": state["messages"]  # Pass through
        }
    
    workflow.add_node("switch_to_comparison", switch_to_comparison)
    workflow.add_node("switch_to_comparison_enricher", switch_to_comparison_enricher)
    
    # Transition nodes always route to next agent
    workflow.add_edge("switch_to_comparison", "splunkagent")
    workflow.add_edge("switch_to_comparison_enricher", "orderenricheragent")
    
    # Add all agent nodes dynamically (including Order Enricher and Summarization)
    for agent_name, agent_instance in supervisor.agents.items():
        node_name = agent_name.lower().replace("_", "")
        
        def make_node(agent):
            def node(state):
                result = agent.execute(state)
                result["sender"] = agent.name
                result["investigation_step"] = state.get("investigation_step", 0) + 1
                return result
            return node
        
        workflow.add_node(node_name, make_node(agent_instance))
    
    # Routing functions
    def route_from_supervisor(state):
        """Route from supervisor - check if order enrichment needed"""
        params = state.get("parameters")
        if not params:
            return "synthesize"
        
        intent = params.intent
        order_id = params.order_id if hasattr(params, 'order_id') else None
        
        # Initialize enrichment fields to ensure they exist
        if "aaa_order_id" not in state:
            state["aaa_order_id"] = None
        if "enrichment_flow" not in state:
            state["enrichment_flow"] = False
        if "actual_order_id" not in state:
            state["actual_order_id"] = None
        
        # Check if order enrichment is needed
        # Only for Investigation/Comparison intents that will use Splunk
        if intent in ["Investigation", "Comparison", "Data"]:
            if order_id and needs_enrichment(order_id):
                # Order needs enrichment - route to Order Enricher
                # Note: enrichment_flow will be set by Order Enricher Agent
                return "orderenricheragent"
            else:
                # Order doesn't need enrichment, ensure flags are False/None
                state["aaa_order_id"] = None
                state["enrichment_flow"] = False
        
        # Normal routing for non-enrichment cases
        if intent == "Knowledge":
            return "vectordbagent"
        elif intent == "Data":
            return "splunkagent"
        elif intent == "Monitoring":
            return "monitoringagent"
        elif intent == "CodeAnalysis":
            return "codeagent" if not order_id else "databaseagent"
        elif intent in ["Investigation", "Comparison"]:
            return "splunkagent"
        return "splunkagent"
    
    def needs_enrichment(order_id):
        """Check if order ID needs enrichment (D-prefix with 9 chars after removing dots)"""
        if not order_id:
            return False
        
        # Remove dots
        clean_id = order_id.replace(".", "")
        
        # Check if starts with D and has exactly 9 characters
        return clean_id.startswith("D") and len(clean_id) == 9
    
    def route_from_order_enricher(state):
        """Route after Order Enricher - always go to DB Agent to get actual order ID"""
        return "databaseagent"
    
    def route_after_enrichment_db(state):
        """Route after DB Agent completes enrichment - continue to Splunk"""
        # After enrichment DB call, always proceed to Splunk with actual order ID
        # enrichment_flow flag is already cleared by DB Agent
        return "splunkagent"
    
    def route_next_agent(state):
        """
        Pure routing function - determines next agent
        Handles conditional Splunk routing and enrichment flow
        """
        sender = state.get("sender", "")
        params = state.get("parameters")
        intent = params.intent if params else "Investigation"
        current_inv = state.get("current_investigation", "primary")
        
        # If Summarization Agent just ran, go to synthesis
        if sender == "Summarization_Agent":
            return "synthesize"
        
        # Single agent paths - go to summarization before synthesis
        if intent in ["Knowledge", "Data", "Monitoring"]:
            return "summarizationagent"
        
        # Code analysis
        if intent == "CodeAnalysis":
            if sender == "Database_Agent":
                return "codeagent"
            elif sender == "Code_Agent":
                return "summarizationagent"
            return "summarizationagent"
        
        # Comparison flow - investigate BOTH orders completely
        if intent == "Comparison":
            if current_inv == "primary":
                # Primary order investigation
                if sender == "Splunk_Agent":
                    # Check if Splunk found logs
                    splunk_findings = state.get("findings", {}).get("Splunk_Agent", {})
                    if splunk_findings.get("logs_found", False):
                        # Logs found, skip DB and DebugAPI
                        # Switch to comparison order investigation
                        state["current_investigation"] = "comparison"
                        state["investigation_step"] = 0
                        
                        # Reset enrichment flags for comparison order
                        state["aaa_order_id"] = None
                        state["enrichment_flow"] = False
                        state["actual_order_id"] = None
                        
                        # Check if comparison order needs enrichment
                        comparison_order = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
                        if comparison_order and needs_enrichment(comparison_order):
                            # Don't set enrichment_flow here - let Order Enricher do it
                            return "orderenricheragent"
                        return "splunkagent"
                    else:
                        # No logs, proceed to DB
                        return "databaseagent"
                        
                elif sender == "Database_Agent":
                    return "debugapiagent"
                    
                elif sender == "DebugAPI_Agent":
                    # Primary complete, switch to comparison order
                    state["current_investigation"] = "comparison"
                    state["investigation_step"] = 0
                    
                    # Reset enrichment flags for comparison order
                    state["aaa_order_id"] = None
                    state["enrichment_flow"] = False
                    state["actual_order_id"] = None
                    
                    # Check if comparison order needs enrichment
                    comparison_order = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
                    if comparison_order and needs_enrichment(comparison_order):
                        # Don't set enrichment_flow here - let Order Enricher do it
                        return "orderenricheragent"
                    return "splunkagent"
                    
            elif current_inv == "comparison":
                # Comparison order investigation
                if sender == "Splunk_Agent":
                    # Check if Splunk found logs for comparison order
                    splunk_findings = state.get("findings", {}).get("Splunk_Agent", {})
                    if splunk_findings.get("logs_found", False):
                        # Logs found, skip DB and DebugAPI, go to comparison
                        return "comparisonagent"
                    else:
                        # No logs, proceed to DB
                        return "databaseagent"
                        
                elif sender == "Database_Agent":
                    return "debugapiagent"
                    
                elif sender == "DebugAPI_Agent":
                    # Both orders investigated, now compare
                    return "comparisonagent"
            
            # After comparison analysis
            if sender == "Comparison_Agent":
                return "summarizationagent"
        
        # Investigation flow (single order) - conditional routing based on Splunk results
        if intent == "Investigation":
            if sender == "Splunk_Agent":
                # Check if Splunk found logs
                splunk_findings = state.get("findings", {}).get("Splunk_Agent", {})
                if splunk_findings.get("logs_found", False):
                    # Logs found in Splunk, skip DB and DebugAPI, go straight to Summarization
                    return "summarizationagent"
                else:
                    # No logs found, proceed to Database Agent
                    return "databaseagent"
                    
            elif sender == "Database_Agent":
                return "debugapiagent"
                
            elif sender == "DebugAPI_Agent":
                return "summarizationagent"
        
        return "summarizationagent"
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Supervisor routing - includes order enricher option
    workflow.add_conditional_edges("supervisor", route_from_supervisor, {
        "vectordbagent": "vectordbagent",
        "splunkagent": "splunkagent",
        "databaseagent": "databaseagent",
        "debugapiagent": "debugapiagent",
        "monitoringagent": "monitoringagent",
        "codeagent": "codeagent",
        "orderenricheragent": "orderenricheragent",
        "synthesize": "synthesize"
    })
    
    # Order Enricher always routes to DB Agent
    workflow.add_edge("orderenricheragent", "databaseagent")
    
    # All agents route through the same logic
    for agent_name in supervisor.agents.keys():
        node_name = agent_name.lower().replace("_", "")
        
        # Special handling for Database Agent when coming from Order Enricher
        if node_name == "databaseagent":
            def db_router(state):
                # Check if this DB call is right after Order Enricher (enrichment lookup)
                sender = state.get("sender", "")
                enrichment_just_completed = state.get("actual_order_id") and not state.get("enrichment_flow")
                
                if sender == "Order_Enricher_Agent":
                    # This is enrichment lookup, route to Splunk after
                    return route_after_enrichment_db(state)
                elif enrichment_just_completed and sender == "Database_Agent":
                    # Just completed enrichment in previous DB call, now route based on intent
                    return route_after_enrichment_db(state)
                else:
                    # Normal DB Agent flow (trade fields lookup, etc.)
                    return route_next_agent(state)
            
            workflow.add_conditional_edges(
                node_name,
                db_router,
                {
                    "splunkagent": "splunkagent",
                    "databaseagent": "databaseagent",
                    "debugapiagent": "debugapiagent",
                    "codeagent": "codeagent",
                    "comparisonagent": "comparisonagent",
                    "summarizationagent": "summarizationagent",
                    "synthesize": "synthesize",
                    "switch_to_comparison": "switch_to_comparison",
                    "switch_to_comparison_enricher": "switch_to_comparison_enricher"
                }
            )
        else:
            workflow.add_conditional_edges(
                node_name,
                route_next_agent,
                {
                    "splunkagent": "splunkagent",
                    "databaseagent": "databaseagent",
                    "debugapiagent": "debugapiagent",
                    "codeagent": "codeagent",
                    "comparisonagent": "comparisonagent",
                    "orderenricheragent": "orderenricheragent",
                    "summarizationagent": "summarizationagent",
                    "synthesize": "synthesize",
                    "switch_to_comparison": "switch_to_comparison",
                    "switch_to_comparison_enricher": "switch_to_comparison_enricher"
                }
            )
    
    workflow.add_edge("synthesize", END)
    
    return workflow.compile()
