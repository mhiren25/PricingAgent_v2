"""
Main workflow construction - includes Summarization Agent
"""

from langgraph.graph import StateGraph, END
from src.agents.supervisor_agent import SupervisorAgent
from src.models.state import AgentState


def create_supervisor_graph():
    """Create optimized multi-agent workflow with summarization"""
    
    supervisor = SupervisorAgent()
    workflow = StateGraph(AgentState)
    
    # Add supervisor and synthesis nodes
    workflow.add_node("supervisor", lambda s: supervisor.analyze_query(s))
    workflow.add_node("synthesize", lambda s: supervisor.synthesize_findings(s))
    
    # Add all agent nodes dynamically (including Summarization)
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
        """Route from supervisor to first agent"""
        params = state.get("parameters")
        if not params:
            return "synthesize"
        
        intent = params.intent
        if intent == "Knowledge":
            return "vectordbagent"
        elif intent == "Data":
            return "splunkagent"
        elif intent == "Monitoring":
            return "monitoringagent"
        elif intent == "CodeAnalysis":
            return "codeagent" if not params.order_id else "databaseagent"
        elif intent in ["Investigation", "Comparison"]:
            return "splunkagent"
        return "splunkagent"
    
    def route_next_agent(state):
        """
        Pure routing function - determines next agent
        ALWAYS routes to Summarization Agent before final synthesis
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
        
        # Comparison flow
        if intent == "Comparison":
            if current_inv == "primary":
                if sender == "Splunk_Agent":
                    return "databaseagent"
                elif sender == "Database_Agent":
                    return "debugapiagent"
                elif sender == "DebugAPI_Agent":
                    state["current_investigation"] = "comparison"
                    return "splunkagent"
            elif current_inv == "comparison":
                if sender == "Splunk_Agent":
                    return "databaseagent"
                elif sender == "Database_Agent":
                    return "debugapiagent"
                elif sender == "DebugAPI_Agent":
                    return "comparisonagent"
            if sender == "Comparison_Agent":
                return "summarizationagent"  # Summarize before synthesis
        
        # Investigation flow
        if intent == "Investigation":
            if sender == "Splunk_Agent":
                return "databaseagent"
            elif sender == "Database_Agent":
                return "debugapiagent"
            elif sender == "DebugAPI_Agent":
                return "summarizationagent"  # Summarize before synthesis
        
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
        "synthesize": "synthesize"
    })
    
    # All agents route through the same logic (including to summarization)
    for agent_name in supervisor.agents.keys():
        workflow.add_conditional_edges(
            agent_name.lower().replace("_", ""),
            route_next_agent,
            {
                "splunkagent": "splunkagent",
                "databaseagent": "databaseagent",
                "debugapiagent": "debugapiagent",
                "codeagent": "codeagent",
                "comparisonagent": "comparisonagent",
                "summarizationagent": "summarizationagent",  # NEW route
                "synthesize": "synthesize"
            }
        )
    
    workflow.add_edge("synthesize", END)
    
    return workflow.compile()
