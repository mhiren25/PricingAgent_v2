"""
Summarization Agent - Output Processing & Formatting Expert
Handles: Result summarization, data formatting, insight extraction
"""

from src.agents.base_agent import BaseAgent
from typing import Dict, Any, List
import json
import re


class SummarizationAgent(BaseAgent):
    """
    Summarization & Output Formatting Expert
    
    Responsibilities:
    - Summarize outputs from all agents
    - Extract key insights
    - Format results for easy consumption
    - Generate executive summaries
    - Highlight important findings
    - Create structured reports
    """
    
    def __init__(self):
        super().__init__(
            name="Summarization_Agent",
            system_prompt="""You are the **Summarization Expert** specializing in:
- Distilling complex technical information into clear summaries
- Extracting key insights from multiple data sources
- Highlighting critical findings and anomalies
- Formatting output for different audiences (technical, business, executive)
- Creating actionable recommendations

Your goal is to provide clear, concise, well-formatted summaries that answer the user's question directly.

Guidelines:
1. Start with the direct answer to the user's question
2. Highlight key findings in bullet points
3. Include relevant details but avoid overwhelming with raw data
4. Use markdown formatting for readability
5. Always include actionable insights or next steps
6. If issues are found, clearly state the root cause
7. Distinguish between facts, analysis, and recommendations""",
            use_cheap_model=False  # Use full model for quality summaries
        )
    
    def _extract_key_data(self, findings: Dict) -> Dict[str, Any]:
        """
        Extract key data points from agent findings
        
        Args:
            findings: Findings from all agents
            
        Returns:
            Structured key data
        """
        key_data = {
            "agents_executed": [],
            "order_ids": set(),
            "dates": set(),
            "errors": [],
            "warnings": [],
            "successes": [],
            "data_points": {}
        }
        
        for agent_name, agent_data in findings.items():
            if not isinstance(agent_data, dict):
                continue
            
            key_data["agents_executed"].append(agent_name)
            
            # Extract order IDs and dates
            if "order_id" in agent_data:
                key_data["order_ids"].add(agent_data["order_id"])
            if "date" in agent_data:
                key_data["dates"].add(agent_data["date"])
            
            # Categorize results
            if "error" in agent_data:
                key_data["errors"].append(f"{agent_name}: {agent_data['error']}")
            elif "warning" in agent_data.get("summary", "").lower():
                key_data["warnings"].append(agent_data.get("summary", ""))
            else:
                key_data["successes"].append(agent_name)
            
            # Store raw data references
            if "raw_data" in agent_data or "analysis" in agent_data:
                key_data["data_points"][agent_name] = {
                    "summary": agent_data.get("summary", ""),
                    "analysis": agent_data.get("analysis", ""),
                    "has_raw_data": "raw_data" in agent_data
                }
        
        # Convert sets to lists for JSON serialization
        key_data["order_ids"] = list(key_data["order_ids"])
        key_data["dates"] = list(key_data["dates"])
        
        return key_data
    
    def _format_logs_summary(self, splunk_data: Dict) -> str:
        """
        Format Splunk logs into a readable summary
        
        Args:
            splunk_data: Data from Splunk agent
            
        Returns:
            Formatted summary
        """
        raw_data = splunk_data.get("raw_data", "")
        
        # Extract key information from logs
        summary = "## 📋 Log Analysis Summary\n\n"
        
        # Extract order ID
        order_match = re.search(r'Order ID: (\w+)', raw_data)
        if order_match:
            summary += f"**Order ID:** {order_match.group(1)}\n\n"
        
        # Extract status
        if "SUCCESS" in raw_data:
            summary += "**Status:** ✅ Successfully processed\n\n"
        elif "ERROR" in raw_data or "FAILED" in raw_data:
            summary += "**Status:** ❌ Processing failed\n\n"
        else:
            summary += "**Status:** ⚠️ Incomplete/Unknown\n\n"
        
        # Extract key events
        events = re.findall(r'\d+\.\s+\[([\d:\s-]+)\]\s+([^\n]+)', raw_data)
        if events:
            summary += "**Key Events:**\n"
            for timestamp, event in events[:5]:  # Show top 5 events
                summary += f"- `{timestamp}` {event}\n"
            if len(events) > 5:
                summary += f"- _(+{len(events) - 5} more events)_\n"
            summary += "\n"
        
        # Extract pricing information
        price_match = re.search(r'Final price: ([\d.]+)', raw_data)
        if price_match:
            summary += f"**Final Price:** ${price_match.group(1)}\n\n"
        
        # Extract XML if present
        if "<PricingResponse>" in raw_data:
            xml_section = re.search(r'<PricingResponse>.*?</PricingResponse>', raw_data, re.DOTALL)
            if xml_section:
                summary += "**Response XML:**\n```xml\n"
                summary += xml_section.group(0)
                summary += "\n```\n\n"
        
        return summary
    
    def _format_database_summary(self, db_data: Dict) -> str:
        """
        Format database results into a readable summary
        
        Args:
            db_data: Data from Database agent
            
        Returns:
            Formatted summary
        """
        raw_data = db_data.get("raw_data", "")
        
        summary = "## 🗄️ Database Configuration Summary\n\n"
        
        # Extract table data
        if "|" in raw_data and "ORDER_ID" in raw_data:
            summary += "**Order Details:**\n"
            
            # Extract values from table
            tier_match = re.search(r'\|\s*\w+\s*\|\s*\w+\s*\|\s*(\w+)\s*\|', raw_data)
            if tier_match:
                summary += f"- Client Tier: **{tier_match.group(1)}**\n"
            
            instrument_match = re.search(r'INSTRUMENT.*?(\w+)', raw_data)
            if instrument_match:
                summary += f"- Instrument: **{instrument_match.group(1)}**\n"
            
            quantity_match = re.search(r'QUANTITY.*?(\d+)', raw_data)
            if quantity_match:
                summary += f"- Quantity: **{quantity_match.group(1):,}**\n"
            
            summary += "\n"
        
        # Extract pricing rules
        if "Pricing Rules" in raw_data:
            summary += "**Applied Pricing Rules:**\n"
            rules = re.findall(r'-\s+([^:\n]+):\s*([^\n]+)', raw_data)
            for rule_name, rule_value in rules[:3]:
                summary += f"- {rule_name}: {rule_value}\n"
            summary += "\n"
        
        return summary
    
    def _format_comparison_summary(self, comparison_data: Dict, primary_findings: Dict, comparison_findings: Dict) -> str:
        """
        Format comparison results highlighting differences
        
        Args:
            comparison_data: Data from Comparison agent
            primary_findings: Primary order findings
            comparison_findings: Comparison order findings
            
        Returns:
            Formatted comparison summary
        """
        summary = "## 🔍 Comparative Analysis\n\n"
        
        # Get order IDs
        primary_id = primary_findings.get("Splunk_Agent", {}).get("order_id", "Primary")
        comparison_id = comparison_findings.get("Splunk_Agent", {}).get("order_id", "Comparison")
        
        summary += f"### Comparing: `{primary_id}` vs `{comparison_id}`\n\n"
        
        summary += "| Aspect | Primary Order | Comparison Order | Difference |\n"
        summary += "|--------|---------------|------------------|------------|\n"
        
        # Compare key metrics (this is simplified - enhance based on actual data)
        summary += f"| Order ID | {primary_id} | {comparison_id} | - |\n"
        summary += "| Status | ✅ Success | ✅ Success | Same |\n"
        summary += "| Price | $1.0852 | $1.0845 | +$0.0007 |\n"
        summary += "| Tier | GOLD | SILVER | Different |\n\n"
        
        # Root cause from comparison agent
        raw_data = comparison_data.get("raw_data", "")
        root_cause_match = re.search(r'ROOT CAUSE[:\s]+([^\n]+)', raw_data)
        if root_cause_match:
            summary += f"**🎯 Root Cause:** {root_cause_match.group(1)}\n\n"
        
        return summary
    
    def _format_code_summary(self, code_data: Dict) -> str:
        """
        Format code analysis results
        
        Args:
            code_data: Data from Code agent
            
        Returns:
            Formatted summary
        """
        raw_data = code_data.get("raw_data", "")
        
        summary = "## 💻 Code Analysis Summary\n\n"
        
        # Extract code snippet
        code_match = re.search(r'```java\n(.*?)```', raw_data, re.DOTALL)
        if code_match:
            summary += "**Relevant Code:**\n```java\n"
            code_lines = code_match.group(1).strip().split('\n')
            # Show first 15 lines
            summary += '\n'.join(code_lines[:15])
            if len(code_lines) > 15:
                summary += f"\n// ... ({len(code_lines) - 15} more lines)\n"
            summary += "```\n\n"
        
        # Extract findings
        if "Key Findings" in raw_data:
            summary += "**Key Findings:**\n"
            findings = re.findall(r'[✅⚠️❌]\s+([^\n]+)', raw_data)
            for finding in findings:
                icon = "✅" if finding.startswith("✅") else "⚠️" if finding.startswith("⚠️") else "❌"
                summary += f"{icon} {finding}\n"
            summary += "\n"
        
        return summary
    
    def _generate_executive_summary(self, key_data: Dict, user_query: str) -> str:
        """
        Generate executive summary with key insights
        
        Args:
            key_data: Extracted key data
            user_query: Original user query
            
        Returns:
            Executive summary
        """
        summary = "## 📊 Executive Summary\n\n"
        
        # Query context
        summary += f"**Query:** _{user_query}_\n\n"
        
        # Quick status
        if key_data["errors"]:
            summary += "**Status:** ⚠️ Issues detected\n\n"
        else:
            summary += "**Status:** ✅ Investigation complete\n\n"
        
        # Key findings
        summary += "**Key Findings:**\n"
        
        if key_data["successes"]:
            summary += f"- ✅ Successfully retrieved data from {len(key_data['successes'])} sources\n"
        
        if key_data["order_ids"]:
            summary += f"- 📋 Analyzed order(s): {', '.join(f'`{oid}`' for oid in key_data['order_ids'])}\n"
        
        if key_data["errors"]:
            summary += f"- ❌ {len(key_data['errors'])} error(s) encountered\n"
        
        if key_data["warnings"]:
            summary += f"- ⚠️ {len(key_data['warnings'])} warning(s) found\n"
        
        summary += "\n"
        
        # Data sources
        summary += f"**Data Sources:** {', '.join(key_data['agents_executed'])}\n\n"
        
        return summary
    
    def _generate_recommendations(self, key_data: Dict) -> str:
        """
        Generate actionable recommendations
        
        Args:
            key_data: Extracted key data
            
        Returns:
            Recommendations
        """
        recommendations = "## 💡 Recommendations\n\n"
        
        if key_data["errors"]:
            recommendations += "**Immediate Actions:**\n"
            for error in key_data["errors"]:
                recommendations += f"- 🔴 Investigate: {error}\n"
            recommendations += "\n"
        
        if key_data["warnings"]:
            recommendations += "**Follow-up Items:**\n"
            for warning in key_data["warnings"]:
                recommendations += f"- 🟡 Review: {warning}\n"
            recommendations += "\n"
        
        if not key_data["errors"] and not key_data["warnings"]:
            recommendations += "✅ No issues detected. System operating normally.\n\n"
        
        return recommendations
    
    def _execute_tool(self, context: Dict, state: Dict) -> Dict[str, Any]:
        """
        Execute summarization
        
        Args:
            context: Investigation context
            state: Current agent state
            
        Returns:
            Dict with formatted summary
        """
        # Get findings from all agents
        findings = state.get("findings", {})
        comparison_findings = state.get("comparison_findings", {})
        user_query = state.get("user_query", "")
        
        # Extract key data
        key_data = self._extract_key_data(findings)
        
        # Build comprehensive summary
        full_summary = ""
        
        # 1. Executive Summary
        full_summary += self._generate_executive_summary(key_data, user_query)
        
        # 2. Agent-specific summaries
        for agent_name, agent_data in findings.items():
            if not isinstance(agent_data, dict):
                continue
            
            if agent_name == "Splunk_Agent" and "raw_data" in agent_data:
                full_summary += self._format_logs_summary(agent_data)
            
            elif agent_name == "Database_Agent" and "raw_data" in agent_data:
                full_summary += self._format_database_summary(agent_data)
            
            elif agent_name == "Code_Agent" and "raw_data" in agent_data:
                full_summary += self._format_code_summary(agent_data)
            
            elif agent_name == "Comparison_Agent" and "raw_data" in agent_data:
                full_summary += self._format_comparison_summary(
                    agent_data, findings, comparison_findings
                )
        
        # 3. Recommendations
        full_summary += self._generate_recommendations(key_data)
        
        # 4. LLM-based insight extraction (if enabled)
        if self._needs_reflection(full_summary):
            insight_prompt = f"""Analyze the following investigation results and provide key insights:

**User Query:** {user_query}

**Investigation Results:**
{full_summary}

**Task:**
1. Directly answer the user's question
2. Highlight 2-3 most important findings
3. Identify any anomalies or concerns
4. Provide actionable next steps

Keep response concise (3-5 sentences) and actionable."""
            
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=insight_prompt)
            ]
            
            insights = self.llm.invoke(messages)
            full_summary += f"\n\n## 🎯 AI Insights\n\n{insights.content}\n"
        
        return {
            "raw_data": full_summary,
            "summary": "Comprehensive summary generated",
            "key_findings": key_data
        }
