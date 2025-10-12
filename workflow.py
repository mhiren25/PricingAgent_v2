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
        
        # Check if order enrichment is needed
        # Only for Investigation/Comparison intents that will use Splunk
        if intent in ["Investigation", "Comparison", "Data"]:
            if order_id and needs_enrichment(order_id):
                # Set enrichment flag and route to Order Enricher first
                state["enrichment_flow"] = True
                return "orderenricheragent"
            else:
                # Order doesn't need enrichment, set aaa_order_id as None
                state["aaa_order_id"] = None
        
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
        """Route after DB Agent in enrichment flow - continue with normal flow"""
        sender = state.get("sender", "")
        params = state.get("parameters")
        intent = params.intent if params else "Investigation"
        
        # After enrichment DB call, proceed to Splunk with actual order ID
        if state.get("enrichment_flow", False):
            # Clear enrichment flag and continue normal investigation
            state["enrichment_flow"] = False
            return "splunkagent"
        
        # Normal DB Agent flow (non-enrichment)
        return route_next_agent(state)
    
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
                        
                        # Check if comparison order needs enrichment
                        comparison_order = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
                        if comparison_order and needs_enrichment(comparison_order):
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
                    
                    # Check if comparison order needs enrichment
                    comparison_order = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
                    if comparison_order and needs_enrichment(comparison_order):
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
        
        # Special handling for Database Agent to support enrichment flow
        if node_name == "databaseagent":
            workflow.add_conditional_edges(
                node_name,
                lambda state: route_after_enrichment_db(state) if state.get("enrichment_flow") else route_next_agent(state),
                {
                    "splunkagent": "splunkagent",
                    "databaseagent": "databaseagent",
                    "debugapiagent": "debugapiagent",
                    "codeagent": "codeagent",
                    "comparisonagent": "comparisonagent",
                    "summarizationagent": "summarizationagent",
                    "synthesize": "synthesize"
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
                    "synthesize": "synthesize"
                }
            )
    
    workflow.add_edge("synthesize", END)
    
    return workflow.compile()
