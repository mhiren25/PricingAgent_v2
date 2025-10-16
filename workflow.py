"""
Main workflow construction - Complete Fixed Version
Includes: Order Enrichment, Date Handling, Comparison Flow, Proper State Management
"""

from langgraph.graph import StateGraph, END
from src.agents.supervisor_agent import SupervisorAgent
from src.models.state import AgentState


def create_supervisor_graph():
    """Create optimized multi-agent workflow with all fixes"""
    
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
    
    # Add all agent nodes dynamically
    for agent_name, agent_instance in supervisor.agents.items():
        node_name = agent_name.lower().replace("_", "")
        
        def make_node(agent):
            def node(state):
                result = agent.execute(state)
                # DON'T increment investigation_step here - it causes double increment
                # Just pass through the result
                return result
            return node
        
        workflow.add_node(node_name, make_node(agent_instance))
    
    # Helper function to check if order needs enrichment
    def needs_enrichment(order_id):
        """Check if order ID needs enrichment (D-prefix with 9 chars after removing dots)"""
        if not order_id:
            return False
        clean_id = order_id.replace(".", "")
        return clean_id.startswith("D") and len(clean_id) == 9
    
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
        if intent in ["Investigation", "Comparison", "Data"]:
            if order_id and needs_enrichment(order_id):
                # Order needs enrichment - route to Order Enricher
                return "orderenricheragent"
            else:
                # Order doesn't need enrichment
                pass  # Continue to normal routing
        
        # Normal routing
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
    
    def route_after_enrichment_db(state):
        """Route after DB Agent completes enrichment - continue to Splunk"""
        return "splunkagent"
    
    def route_next_agent(state):
        """
        Pure routing function - determines next agent
        IMPORTANT: Use messages to determine last agent, not sender field (which may not be updated yet)
        """
        # Get the ACTUAL last agent from messages (more reliable than sender field)
        messages = state.get("messages", [])
        sender = None
        for msg in reversed(messages):
            if hasattr(msg, 'name') and msg.name and msg.name != "Supervisor":
                sender = msg.name
                break
        
        if not sender:
            sender = state.get("sender", "")
        
        params = state.get("parameters")
        intent = params.intent if params else "Investigation"
        current_inv = state.get("current_investigation", "primary")
        step = state.get("investigation_step", 0)
        
        # DEBUG LOGGING
        print(f"\n{'='*60}")
        print(f"[ROUTING] Step {step}")
        print(f"  Sender (from messages): {sender}")
        print(f"  Intent: {intent}")
        print(f"  Investigation Phase: {current_inv}")
        print(f"  Enrichment Flow: {state.get('enrichment_flow', False)}")
        print(f"  Actual Order ID: {state.get('actual_order_id')}")
        print(f"{'='*60}")
        
        # If Summarization Agent just ran, go to synthesis
        if sender == "Summarization_Agent":
            print(f"[ROUTING] → synthesize (from Summarization Agent)")
            return "synthesize"
        
        # Single agent paths
        if intent in ["Knowledge", "Data", "Monitoring"]:
            print(f"[ROUTING] → summarizationagent (simple intent)")
            return "summarizationagent"
        
        # Code analysis
        if intent == "CodeAnalysis":
            if sender == "Database_Agent":
                print(f"[ROUTING] → codeagent")
                return "codeagent"
            elif sender == "Code_Agent":
                print(f"[ROUTING] → summarizationagent")
                return "summarizationagent"
            print(f"[ROUTING] → summarizationagent (fallback)")
            return "summarizationagent"
        
        # COMPARISON FLOW
        if intent == "Comparison":
            print(f"\n[COMPARISON FLOW] Phase: {current_inv}, Sender: {sender}")
            
            if current_inv == "primary":
                print(f"[PRIMARY INVESTIGATION]")
                
                if sender == "Splunk_Agent":
                    print(f"[PRIMARY] Splunk completed - switch to comparison phase")
                    comparison_order = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
                    print(f"[PRIMARY] Comparison order: {comparison_order}")
                    
                    if comparison_order and needs_enrichment(comparison_order):
                        print(f"[PRIMARY] → switch_to_comparison_enricher")
                        return "switch_to_comparison_enricher"
                    
                    print(f"[PRIMARY] → switch_to_comparison")
                    return "switch_to_comparison"
                
                elif sender == "Order_Enricher_Agent":
                    print(f"[PRIMARY] → databaseagent (after Order Enricher)")
                    return "databaseagent"
                
                elif sender == "Database_Agent":
                    enrichment_completed = state.get("actual_order_id") is not None
                    enrichment_active = state.get("enrichment_flow", False)
                    
                    print(f"[PRIMARY] DB Agent - enrichment_completed: {enrichment_completed}, enrichment_active: {enrichment_active}")
                    
                    # Check message history to determine context
                    messages = state.get("messages", [])
                    recent_agents = [msg.name for msg in messages[-5:] if hasattr(msg, 'name')]
                    print(f"[PRIMARY] Recent agents: {recent_agents}")
                    
                    if "Splunk_Agent" in recent_agents:
                        print(f"[PRIMARY] → debugapiagent (DB called after Splunk for trade fields)")
                        return "debugapiagent"
                    elif enrichment_completed and not enrichment_active:
                        print(f"[PRIMARY] → splunkagent (after enrichment)")
                        return "splunkagent"
                    else:
                        print(f"[PRIMARY] → debugapiagent (fallback)")
                        return "debugapiagent"
                
                elif sender == "DebugAPI_Agent":
                    print(f"[PRIMARY] DebugAPI completed - switch to comparison phase")
                    comparison_order = params.comparison_order_id if hasattr(params, 'comparison_order_id') else None
                    
                    if comparison_order and needs_enrichment(comparison_order):
                        print(f"[PRIMARY] → switch_to_comparison_enricher")
                        return "switch_to_comparison_enricher"
                    
                    print(f"[PRIMARY] → switch_to_comparison")
                    return "switch_to_comparison"
            
            elif current_inv == "comparison":
                print(f"[COMPARISON INVESTIGATION]")
                
                if sender == "Splunk_Agent":
                    comparison_splunk = state.get("comparison_findings", {}).get("Splunk_Agent", {})
                    logs_found = comparison_splunk.get("logs_found", False)
                    
                    print(f"[COMPARISON] Splunk completed - logs_found: {logs_found}")
                    print(f"[COMPARISON] → comparisonagent (both orders investigated)")
                    return "comparisonagent"
                
                elif sender == "Order_Enricher_Agent":
                    print(f"[COMPARISON] → databaseagent (after Order Enricher)")
                    return "databaseagent"
                
                elif sender == "Database_Agent":
                    enrichment_completed = state.get("comparison_actual_order_id") is not None
                    enrichment_active = state.get("comparison_enrichment_flow", False)
                    
                    print(f"[COMPARISON] DB Agent - enrichment_completed: {enrichment_completed}, enrichment_active: {enrichment_active}")
                    
                    # Check message history
                    messages = state.get("messages", [])
                    recent_agents = [msg.name for msg in messages[-5:] if hasattr(msg, 'name')]
                    print(f"[COMPARISON] Recent agents: {recent_agents}")
                    
                    if "Splunk_Agent" in recent_agents:
                        print(f"[COMPARISON] → debugapiagent (DB called after Splunk for trade fields)")
                        return "debugapiagent"
                    elif enrichment_completed and not enrichment_active:
                        print(f"[COMPARISON] → splunkagent (after enrichment)")
                        return "splunkagent"
                    else:
                        print(f"[COMPARISON] → debugapiagent (fallback)")
                        return "debugapiagent"
                
                elif sender == "DebugAPI_Agent":
                    print(f"[COMPARISON] DebugAPI completed")
                    print(f"[COMPARISON] → comparisonagent (both orders investigated)")
                    return "comparisonagent"
            
            if sender == "Comparison_Agent":
                print(f"[ROUTING] → summarizationagent (after Comparison Agent)")
                return "summarizationagent"
        
        # INVESTIGATION FLOW (single order)
        if intent == "Investigation":
            print(f"\n[INVESTIGATION FLOW] Sender: {sender}")
            
            if sender == "Order_Enricher_Agent":
                print(f"[INVESTIGATION] → databaseagent (after Order Enricher)")
                return "databaseagent"
            
            elif sender == "Splunk_Agent":
                splunk_findings = state.get("findings", {}).get("Splunk_Agent", {})
                logs_found = splunk_findings.get("logs_found", False)
                
                print(f"[INVESTIGATION] Splunk logs_found: {logs_found}")
                
                if logs_found:
                    print(f"[INVESTIGATION] → summarizationagent (logs found)")
                    return "summarizationagent"
                else:
                    print(f"[INVESTIGATION] → databaseagent (no logs, need trade fields)")
                    return "databaseagent"
            
            elif sender == "Database_Agent":
                enrichment_completed = state.get("actual_order_id") is not None
                enrichment_active = state.get("enrichment_flow", False)
                
                print(f"[INVESTIGATION] DB Agent - enrichment_completed: {enrichment_completed}, enrichment_active: {enrichment_active}")
                
                # Check message history to determine context
                messages = state.get("messages", [])
                recent_agents = [msg.name for msg in messages[-5:] if hasattr(msg, 'name')]
                print(f"[INVESTIGATION] Recent agents: {recent_agents}")
                
                # If Splunk was called before this DB call, we're getting trade fields
                if "Splunk_Agent" in recent_agents:
                    print(f"[INVESTIGATION] → debugapiagent (DB called after Splunk for trade fields)")
                    return "debugapiagent"
                elif enrichment_completed and not enrichment_active:
                    print(f"[INVESTIGATION] → splunkagent (after enrichment)")
                    return "splunkagent"
                else:
                    print(f"[INVESTIGATION] → debugapiagent (fallback)")
                    return "debugapiagent"
            
            elif sender == "DebugAPI_Agent":
                print(f"[INVESTIGATION] → summarizationagent")
                return "summarizationagent"
        
        print(f"[ROUTING] → summarizationagent (fallback)")
        return "summarizationagent"
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Supervisor routing
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
    
    # All agents route through the same logic
    for agent_name in supervisor.agents.keys():
        node_name = agent_name.lower().replace("_", "")
        
        # Special handling for Database Agent when coming from Order Enricher
        if node_name == "databaseagent":
            def db_router(state):
                # Get the ACTUAL last agent from messages (more reliable than sender field)
                messages = state.get("messages", [])
                sender = None
                for msg in reversed(messages):
                    if hasattr(msg, 'name') and msg.name and msg.name != "Supervisor":
                        sender = msg.name
                        break
                
                print(f"\n[DB_ROUTER] Last agent from messages: {sender}")
                
                # Check if DB was called right after Order Enricher
                if sender == "Order_Enricher_Agent":
                    print(f"[DB_ROUTER] → splunkagent (after enrichment)")
                    return "splunkagent"
                
                # For all other cases, use normal routing logic
                print(f"[DB_ROUTER] → route_next_agent (normal flow)")
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
