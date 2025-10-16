"""
Summarization Agent - LLM-powered comprehensive summary generation
Analyzes all agent findings and creates detailed, actionable summaries
"""

from src.agents.base_agent import BaseAgent
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage


class SummarizationAgent(BaseAgent):
    """
    Summarization Expert - Creates comprehensive summaries using LLM
    
    Responsibilities:
    - Analyze findings from all agents
    - Generate detailed, structured summaries
    - Highlight key insights and anomalies
    - Provide actionable recommendations
    """
    
    def __init__(self):
        super().__init__(
            name="Summarization_Agent",
            system_prompt="""You are a **Senior Technical Analyst** specializing in:
- Synthesizing complex technical data into clear, actionable summaries
- Identifying patterns, anomalies, and root causes
- Providing structured analysis with key findings
- Creating executive-ready summaries with technical depth

Your summaries should be:
- **Comprehensive**: Cover all important findings
- **Structured**: Use clear sections and formatting
- **Actionable**: Highlight issues and next steps
- **Accurate**: Preserve technical details while being accessible
- **Insightful**: Connect dots between different agent findings

Always provide a summary that both technical and non-technical stakeholders can understand.""",
            use_cheap_model=False  # Use powerful model for quality summaries
        )
    
    def _extract_all_findings(self, state: Dict) -> Dict[str, Any]:
        """
        Extract and organize findings from all agents
        
        Args:
            state: Current agent state
            
        Returns:
            Dictionary of organized findings
        """
        findings = state.get("findings", {})
        comparison_findings = state.get("comparison_findings", {})
        params = state.get("parameters")
        
        return {
            "primary_findings": findings,
            "comparison_findings": comparison_findings,
            "intent": params.intent if params else "Unknown",
            "order_id": params.order_id if params else "",
            "date": params.date if params else "",
            "comparison_order_id": params.comparison_order_id if params else "",
            "comparison_date": params.comparison_date if params else "",
            "user_query": state.get("user_query", ""),
            "enriched": state.get("actual_order_id") is not None
        }
    
    def _format_agent_findings(self, findings: Dict[str, Any]) -> str:
        """
        Format agent findings into readable text for LLM
        
        Args:
            findings: Agent findings dictionary
            
        Returns:
            Formatted string of findings
        """
        formatted_sections = []
        
        # Track which agents we've seen to handle duplicates (e.g., DB Agent called twice)
        agent_call_count = {}
        
        for agent_name, agent_data in findings.items():
            if not isinstance(agent_data, dict):
                continue
            
            # Count occurrences of each agent
            if agent_name not in agent_call_count:
                agent_call_count[agent_name] = 0
            agent_call_count[agent_name] += 1
            
            # Add call number for agents called multiple times
            display_name = agent_name
            if agent_call_count[agent_name] > 1:
                # Check if this is enrichment vs normal call
                if agent_name == "Database_Agent":
                    if agent_data.get("enrichment_completed"):
                        display_name = f"{agent_name} (Enrichment Lookup)"
                    else:
                        display_name = f"{agent_name} (Trade Data Retrieval)"
                else:
                    display_name = f"{agent_name} (Call #{agent_call_count[agent_name]})"
            
            section = f"\n## {display_name}\n"
            
            # Add summary if available
            if "summary" in agent_data:
                section += f"**Summary:** {agent_data['summary']}\n\n"
            
            # Add analysis if available
            if "analysis" in agent_data:
                section += f"**Analysis:** {agent_data['analysis']}\n\n"
            
            # Add raw data if available (truncate if too long)
            if "raw_data" in agent_data:
                raw_data = str(agent_data["raw_data"])
                if len(raw_data) > 2000:
                    raw_data = raw_data[:2000] + "\n... (truncated)"
                section += f"**Details:**\n{raw_data}\n"
            
            # Add key fields
            for key in ["order_id", "logs_found", "enriched", "status", "enrichment_completed", "actual_order_id"]:
                if key in agent_data and agent_data[key] is not None:
                    section += f"- **{key.replace('_', ' ').title()}:** {agent_data[key]}\n"
            
            formatted_sections.append(section)
        
        return "\n".join(formatted_sections)
    
    def _generate_summary_prompt(self, all_findings: Dict[str, Any]) -> str:
        """
        Generate the prompt for LLM summarization
        
        Args:
            all_findings: All findings from agents
            
        Returns:
            Formatted prompt string
        """
        intent = all_findings["intent"]
        user_query = all_findings["user_query"]
        
        # Format primary findings
        primary_formatted = self._format_agent_findings(all_findings["primary_findings"])
        
        # Base prompt
        prompt = f"""# Investigation Summary Request

**User Query:** {user_query}
**Intent:** {intent}

## Context
"""
        
        # Add order context
        if all_findings["order_id"]:
            prompt += f"- **Order ID:** {all_findings['order_id']}"
            if all_findings["enriched"]:
                prompt += " ✅ (Enriched from D-prefix)"
            prompt += f"\n- **Date:** {all_findings['date']}\n"
        
        # Add comparison context if applicable
        if intent == "Comparison" and all_findings["comparison_order_id"]:
            prompt += f"- **Comparison Order ID:** {all_findings['comparison_order_id']}\n"
            prompt += f"- **Comparison Date:** {all_findings['comparison_date']}\n"
        
        # Add primary findings
        prompt += f"\n## Agent Findings\n{primary_formatted}\n"
        
        # Add comparison findings if available
        if all_findings["comparison_findings"]:
            comparison_formatted = self._format_agent_findings(all_findings["comparison_findings"])
            prompt += f"\n## Comparison Order Findings\n{comparison_formatted}\n"
        
        # Add instructions
        prompt += """
---

## Your Task

Create a **comprehensive, executive-ready summary** that includes:

### 1. Executive Summary (2-3 sentences)
A high-level overview of what was investigated and the key outcome.

### 2. Key Findings
List the most important discoveries, organized by topic:
- Order processing status
- Any errors or issues identified
- Performance metrics
- Configuration details

### 3. Technical Details
Provide relevant technical information:
- Splunk log analysis (if available)
- Database query results
- API responses
- System health metrics

### 4. Issues & Anomalies (if any)
Highlight any problems discovered:
- Error messages
- Unexpected behavior
- Performance issues
- Configuration problems

### 5. Recommendations (if applicable)
Suggest next steps or actions based on findings.

### 6. Comparison Analysis (for comparison intent only)
If this is a comparison, provide:
- Side-by-side analysis of key differences
- Similarities and patterns
- Potential reasons for differences

## Formatting Guidelines
- Use **clear section headers**
- Use bullet points for lists
- **Bold** important terms and values
- Use `code formatting` for technical identifiers (order IDs, error codes)
- Keep it concise but comprehensive
- Focus on actionable insights

Generate the summary now:
"""
        
        return prompt
    
    def _execute_tool(self, context: Dict, state: Dict) -> Dict[str, Any]:
        """
        Generate comprehensive summary using LLM
        
        Args:
            context: Investigation context
            state: Agent state with all findings
            
        Returns:
            Dict with generated summary
        """
        # Extract all findings
        all_findings = self._extract_all_findings(state)
        
        # Check if there are any findings to summarize
        if not all_findings["primary_findings"] and not all_findings["comparison_findings"]:
            return {
                "raw_data": "No findings available to summarize.",
                "summary": "No agent findings were collected."
            }
        
        # Generate summary prompt
        summary_prompt = self._generate_summary_prompt(all_findings)
        
        # Call LLM to generate summary
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=summary_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            detailed_summary = response.content
            
            # Create a brief one-liner for the summary field
            brief_summary = detailed_summary.split('\n')[0][:200] + "..."
            
            return {
                "raw_data": detailed_summary,
                "summary": brief_summary,
                "full_summary": detailed_summary,
                "status": "success"
            }
            
        except Exception as e:
            # Fallback to simple concatenation if LLM fails
            fallback_summary = self._create_fallback_summary(all_findings)
            
            return {
                "raw_data": fallback_summary,
                "summary": "Summary generated using fallback method",
                "error": str(e),
                "status": "fallback"
            }
    
    def _create_fallback_summary(self, all_findings: Dict[str, Any]) -> str:
        """
        Create a simple summary without LLM (fallback)
        
        Args:
            all_findings: All findings from agents
            
        Returns:
            Basic formatted summary
        """
        summary_parts = [
            f"# Investigation Summary\n",
            f"**User Query:** {all_findings['user_query']}\n",
            f"**Intent:** {all_findings['intent']}\n\n"
        ]
        
        # Add order info
        if all_findings["order_id"]:
            summary_parts.append(f"**Order ID:** {all_findings['order_id']}\n")
            summary_parts.append(f"**Date:** {all_findings['date']}\n\n")
        
        # Add findings
        summary_parts.append("## Findings\n\n")
        
        for agent_name, data in all_findings["primary_findings"].items():
            if isinstance(data, dict) and "summary" in data:
                summary_parts.append(f"- **{agent_name}:** {data['summary']}\n")
        
        return "".join(summary_parts)
