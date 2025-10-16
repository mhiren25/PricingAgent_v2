"""
Comparison Agent - Comparative Analysis Expert
Handles: Side-by-side order comparison, diff analysis, root cause identification
Uses LLM with structured output for comprehensive analysis
"""

from src.agents.base_agent import BaseAgent
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
import logging

logger = logging.getLogger(__name__)


# Structured output models
class PricingComponent(BaseModel):
    """Individual pricing component comparison"""
    component: str = Field(description="Name of the pricing component (e.g., 'Base Price', 'Spread', 'Discount')")
    primary_value: str = Field(description="Value in primary order")
    comparison_value: str = Field(description="Value in comparison order")
    difference: str = Field(description="Calculated or observed difference")
    significance: str = Field(description="Impact level: 'Critical', 'Major', 'Minor', or 'None'")


class ConfigurationDifference(BaseModel):
    """Configuration or attribute difference"""
    attribute: str = Field(description="Configuration attribute name (e.g., 'Client Tier', 'Order Type')")
    primary_value: str = Field(description="Value in primary order")
    comparison_value: str = Field(description="Value in comparison order")
    impact: str = Field(description="How this difference affects pricing or behavior")


class RootCause(BaseModel):
    """Identified root cause for discrepancy"""
    cause: str = Field(description="Clear statement of the root cause")
    confidence: str = Field(description="Confidence level: 'High', 'Medium', 'Low'")
    supporting_evidence: List[str] = Field(description="List of evidence supporting this root cause")
    recommendation: str = Field(description="Recommended action or explanation")


class ComparisonSummary(BaseModel):
    """Complete structured comparison analysis"""
    executive_summary: str = Field(description="High-level summary of the comparison (2-3 sentences)")
    pricing_differences: List[PricingComponent] = Field(description="Detailed pricing component comparisons")
    configuration_differences: List[ConfigurationDifference] = Field(description="Configuration and attribute differences")
    root_causes: List[RootCause] = Field(description="Identified root causes ranked by importance")
    overall_assessment: str = Field(description="Final assessment with key takeaways")
    anomalies_detected: List[str] = Field(default_factory=list, description="Any unusual patterns or anomalies")


class ComparisonAgent(BaseAgent):
    """Comparative Analysis Expert with LLM-powered structured analysis"""
    
    def __init__(self):
        super().__init__(
            name="Comparison_Agent",
            system_prompt="""You are the **Comparative Analysis Expert** specializing in:
- Side-by-side order comparison
- Pricing difference analysis  
- Configuration change detection
- Root cause identification for pricing discrepancies

Your job is to identify WHY two orders had different prices by:
1. Comparing all pricing components systematically
2. Identifying configuration differences that impact pricing
3. Determining root causes with supporting evidence
4. Providing clear, actionable insights

Be thorough, analytical, and precise in your comparisons.""",
            use_cheap_model=False  # Use full model for complex analysis
        )
        
        # Create structured LLM for comparison analysis
        self.structured_llm = self.llm.with_structured_output(ComparisonSummary)
    
    def _execute_tool(self, context: Dict, state: Dict) -> Dict[str, Any]:
        """Perform LLM-powered comparative analysis between two orders"""
        
        # Extract findings from both orders
        primary_findings = state.get("findings", {})
        comparison_findings = state.get("comparison_findings", {})
        
        # Get order metadata
        params = state.get("parameters")
        primary_order_id = context.get("order_id", "Unknown")
        comparison_order_id = params.comparison_order_id if params else "Unknown"
        
        # Check if we have sufficient data
        if not primary_findings or not comparison_findings:
            return {
                "raw_data": {"error": "Insufficient data for comparison"},
                "summary": "⚠️ Cannot perform comparison - missing data from one or both orders",
                "comparison_completed": False
            }
        
        # Format findings for LLM analysis
        primary_formatted = self._format_findings_detailed(primary_findings, "PRIMARY")
        comparison_formatted = self._format_findings_detailed(comparison_findings, "COMPARISON")
        
        # Build comprehensive analysis prompt
        analysis_prompt = f"""Perform a comprehensive comparative analysis between two orders.

**PRIMARY ORDER: {primary_order_id}**
{primary_formatted}

**COMPARISON ORDER: {comparison_order_id}**
{comparison_formatted}

**USER QUERY:** {state.get('user_query', 'Compare these orders')}

**ANALYSIS TASKS:**
1. Compare all pricing components (base prices, spreads, discounts, fees, final prices)
2. Identify configuration differences (client tier, order type, routing, etc.)
3. Determine root causes for any pricing discrepancies
4. Assess significance of each difference (Critical/Major/Minor/None)
5. Flag any anomalies or unexpected patterns

Provide a thorough, structured analysis that clearly explains WHY the orders differ."""

        try:
            # Get structured analysis from LLM
            logger.info(f"{self.name}: Generating structured comparison analysis...")
            
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=analysis_prompt)
            ]
            
            structured_result: ComparisonSummary = self.structured_llm.invoke(messages)
            
            # Format the structured output into readable summary
            summary = self._format_structured_summary(structured_result)
            
            # Store both structured and formatted data
            return {
                "raw_data": structured_result.model_dump(),
                "structured_comparison": structured_result.model_dump(),
                "summary": summary,
                "comparison_completed": True,
                "root_causes_count": len(structured_result.root_causes),
                "critical_differences": sum(
                    1 for diff in structured_result.pricing_differences 
                    if diff.significance == "Critical"
                )
            }
            
        except Exception as e:
            logger.error(f"{self.name}: Structured analysis failed: {str(e)}")
            
            # Fallback to simple comparison
            fallback_summary = self._fallback_comparison(
                primary_findings, 
                comparison_findings,
                primary_order_id,
                comparison_order_id
            )
            
            return {
                "raw_data": {"fallback": True, "error": str(e)},
                "summary": fallback_summary,
                "comparison_completed": True,
                "fallback_used": True
            }
    
    def _format_findings_detailed(self, findings: dict, label: str) -> str:
        """Format findings with detailed extraction for LLM analysis"""
        lines = [f"\n=== {label} ORDER FINDINGS ===\n"]
        
        for agent_name, data in findings.items():
            lines.append(f"\n**{agent_name}:**")
            
            # Handle list of findings (multiple calls)
            if isinstance(data, list):
                for idx, item in enumerate(data, 1):
                    lines.append(f"  Call {idx}:")
                    lines.append(f"    Summary: {item.get('summary', 'N/A')}")
                    if item.get('analysis'):
                        lines.append(f"    Analysis: {item['analysis']}")
            
            # Handle single finding dict
            elif isinstance(data, dict):
                lines.append(f"  Summary: {data.get('summary', 'N/A')}")
                if data.get('analysis'):
                    lines.append(f"  Analysis: {data['analysis']}")
                if data.get('logs_found') is not None:
                    lines.append(f"  Logs Found: {data['logs_found']}")
                if data.get('enriched'):
                    lines.append(f"  Order Enriched: Yes")
        
        return "\n".join(lines) if len(lines) > 1 else "No findings available"
    
    def _format_structured_summary(self, result: ComparisonSummary) -> str:
        """Format structured comparison into readable markdown summary"""
        lines = ["## 📊 Comparative Analysis Summary\n"]
        
        # Executive summary
        lines.append(f"**Executive Summary:**")
        lines.append(f"{result.executive_summary}\n")
        
        # Pricing differences
        if result.pricing_differences:
            lines.append("### 💰 Pricing Component Comparison\n")
            for diff in result.pricing_differences:
                significance_emoji = {
                    "Critical": "🔴",
                    "Major": "🟡", 
                    "Minor": "🟢",
                    "None": "⚪"
                }.get(diff.significance, "⚪")
                
                lines.append(f"{significance_emoji} **{diff.component}**")
                lines.append(f"  - Primary: {diff.primary_value}")
                lines.append(f"  - Comparison: {diff.comparison_value}")
                lines.append(f"  - Difference: {diff.difference}\n")
        
        # Configuration differences
        if result.configuration_differences:
            lines.append("### ⚙️ Configuration Differences\n")
            for diff in result.configuration_differences:
                lines.append(f"**{diff.attribute}**")
                lines.append(f"  - Primary: {diff.primary_value}")
                lines.append(f"  - Comparison: {diff.comparison_value}")
                lines.append(f"  - Impact: {diff.impact}\n")
        
        # Root causes
        if result.root_causes:
            lines.append("### 🎯 Root Cause Analysis\n")
            for idx, cause in enumerate(result.root_causes, 1):
                confidence_emoji = {
                    "High": "✅",
                    "Medium": "⚠️",
                    "Low": "❓"
                }.get(cause.confidence, "❓")
                
                lines.append(f"{idx}. {confidence_emoji} **{cause.cause}** (Confidence: {cause.confidence})")
                lines.append(f"   - Evidence:")
                for evidence in cause.supporting_evidence:
                    lines.append(f"     • {evidence}")
                lines.append(f"   - Recommendation: {cause.recommendation}\n")
        
        # Anomalies
        if result.anomalies_detected:
            lines.append("### ⚠️ Anomalies Detected\n")
            for anomaly in result.anomalies_detected:
                lines.append(f"- {anomaly}")
            lines.append("")
        
        # Overall assessment
        lines.append("### 📋 Overall Assessment\n")
        lines.append(result.overall_assessment)
        
        return "\n".join(lines)
    
    def _fallback_comparison(
        self, 
        primary: dict, 
        comparison: dict,
        primary_id: str,
        comparison_id: str
    ) -> str:
        """Simple fallback comparison without LLM"""
        lines = [
            "## 📊 Comparison Summary (Simplified)\n",
            f"**PRIMARY ORDER:** {primary_id}",
            self._format_findings_simple(primary),
            "",
            f"**COMPARISON ORDER:** {comparison_id}",
            self._format_findings_simple(comparison),
            "",
            "⚠️ *Full structured analysis unavailable - showing basic comparison*"
        ]
        return "\n".join(lines)
    
    def _format_findings_simple(self, findings: dict) -> str:
        """Simple formatting for fallback"""
        lines = []
        for agent_name, data in findings.items():
            if isinstance(data, dict) and "summary" in data:
                lines.append(f"  - {agent_name}: {data['summary']}")
        return "\n".join(lines) if lines else "  No findings"
