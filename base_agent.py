"""
Base Agent - Abstract base class for all specialized agents
Provides common functionality: error handling, caching, reflection, retry logic
Updated to support order enrichment flow
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime
import hashlib
import logging

# Import config package (auto-loads .env)
from config import settings

logger = logging.getLogger(__name__)

# Simple in-memory cache (replace with Redis in production)
class SimpleCache:
    def __init__(self):
        self._cache: Dict[str, tuple[Any, datetime]] = {}
    
    def get(self, key: str, ttl_minutes: int = 5) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if (datetime.now() - timestamp).total_seconds() < ttl_minutes * 60:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        self._cache[key] = (value, datetime.now())

CACHE = SimpleCache()


class BaseAgent(ABC):
    """
    Base class with common functionality for all agents
    
    Features:
    - Error handling with retries
    - Caching support
    - Conditional reflection (optimize LLM calls)
    - Investigation context management
    - Structured findings storage
    - Order enrichment support
    """
    
    def __init__(self, name: str, system_prompt: str, use_cheap_model: bool = False):
        """
        Initialize base agent
        
        Args:
            name: Agent name (e.g., "Splunk_Agent")
            system_prompt: System prompt defining agent's role
            use_cheap_model: Use cheaper model (Haiku) for cost optimization
        """
        self.name = name
        self.system_prompt = system_prompt
        
        # Select model based on cost optimization
        model = settings.cheap_model if use_cheap_model else settings.agent_model
        self.llm = ChatAnthropic(
            model=model,
            temperature=settings.model_temperature,
            max_tokens=settings.model_max_tokens
        )
        
        logger.info(f"Initialized {name} with model: {model}")
    
    def _get_investigation_context(self, state: Dict) -> Dict[str, Any]:
        """
        Extract investigation context (primary or comparison order)
        Supports order enrichment flow with separate fields per order
        
        Args:
            state: Current agent state
            
        Returns:
            Context dict with order_id, date, findings_key, prefix
        """
        current_inv = state.get("current_investigation", "primary")
        params = state.get("parameters")
        
        # Check for enriched order ID based on investigation phase
        if current_inv == "comparison":
            actual_order_id = state.get("comparison_actual_order_id")
            enrichment_flow = state.get("comparison_enrichment_flow", False)
        else:
            actual_order_id = state.get("actual_order_id")
            enrichment_flow = state.get("enrichment_flow", False)
        
        if current_inv == "comparison":
            # Comparison order context
            order_id = params.comparison_order_id if params else ""
            
            # Use actual_order_id if available from enrichment
            if actual_order_id and not enrichment_flow:
                order_id = actual_order_id
            
            return {
                "order_id": order_id,
                "date": params.comparison_date if params else "",
                "findings_key": "comparison_findings",
                "prefix": "[COMPARISON ORDER]",
                "enriched": bool(actual_order_id and not enrichment_flow)
            }
        
        # Primary order context
        order_id = params.order_id if params else ""
        
        # Use actual_order_id if available from enrichment
        if actual_order_id and not enrichment_flow:
            order_id = actual_order_id
        
        return {
            "order_id": order_id,
            "date": params.date if params else "",
            "findings_key": "findings",
            "prefix": "[PRIMARY ORDER]",
            "enriched": bool(actual_order_id and not enrichment_flow)
        }
    
    def _get_cache_key(self, *args) -> str:
        """
        Generate cache key from arguments
        
        Args:
            *args: Arguments to hash for cache key
            
        Returns:
            MD5 hash as cache key
        """
        cache_str = f"{self.name}_{'_'.join(str(a) for a in args)}"
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _store_findings(self, state: Dict, findings: Dict, context: Dict):
        """
        Store findings in appropriate state location
        
        Only stores essential data to prevent state bloat.
        Large data stored in cache with reference.
        
        Args:
            state: Agent state
            findings: Findings to store
            context: Investigation context
        """
        findings_key = context["findings_key"]
        
        if findings_key not in state:
            state[findings_key] = {}
        
        # Store only essential data
        state[findings_key][self.name] = {
            "summary": findings.get("summary", ""),
            "analysis": findings.get("analysis", ""),
            "order_id": context.get("order_id"),
            "timestamp": datetime.now().isoformat(),
            "cache_key": findings.get("cache_key"),  # Reference to large data
            "logs_found": findings.get("logs_found"),  # Important for routing
            "enriched": context.get("enriched", False)  # Track if order was enriched
        }
    
    def _needs_reflection(self, tool_output: str) -> bool:
        """
        Determine if LLM reflection is needed
        
        Optimization: Skip reflection for successful, straightforward results
        
        Args:
            tool_output: Output from tool execution
            
        Returns:
            True if reflection needed, False otherwise
        """
        # Always reflect on errors
        if "error" in tool_output.lower():
            return True
        
        # Reflect on complex output
        if len(tool_output) > 5000:
            return True
        
        # Respect configuration
        return settings.enable_reflection
    
    def _reflect(self, findings: Dict, context: Dict, state: Dict) -> str:
        """
        LLM-based reflection on findings
        
        Args:
            findings: Tool execution results
            context: Investigation context
            state: Agent state
            
        Returns:
            Reflection summary
        """
        reflection_prompt = f"""
<Show Your Thinking>
Tool Output: {findings.get('raw_data', findings)}

User Query: {state.get('user_query', '')}
Context: {context.get('prefix', '')}

Analysis:
1. What key information was found?
2. How does this relate to the user's query?
3. Are there any issues or anomalies?
4. What are the key takeaways?
</Show Your Thinking>

Provide a concise, actionable summary (3-5 sentences max).
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=reflection_prompt)
        ]
        
        response = self.llm.invoke(messages)
        return response.content
    
    def _simple_summary(self, findings: Dict) -> str:
        """
        Simple summary without LLM (faster, cheaper)
        
        Args:
            findings: Tool execution results
            
        Returns:
            Simple text summary
        """
        return findings.get("summary", str(findings)[:500])
    
    @abstractmethod
    def _execute_tool(self, context: Dict, state: Dict) -> Dict:
        """
        Execute the agent's main tool - MUST be implemented by subclasses
        
        Args:
            context: Investigation context (includes enriched order ID if available)
            state: Agent state (includes enrichment_flow flag and actual_order_id)
            
        Returns:
            Dict with tool results (should include 'summary' and 'raw_data')
        """
        pass
    
    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    def execute(self, state: Dict) -> Dict:
        """
        Main execution with error handling and retry logic
        
        Workflow:
        1. Get investigation context (with enrichment support)
        2. Check cache (if enabled)
        3. Execute tool
        4. Reflect on results (if needed)
        5. Store findings
        6. Handle errors gracefully
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state
        """
        context = self._get_investigation_context(state)
        prefix = context["prefix"]
        
        # Add enrichment indicator to prefix if order was enriched
        if context.get("enriched"):
            prefix += " 🔧"
        
        try:
            # Check cache first
            if settings.enable_caching:
                cache_key = self._get_cache_key(
                    context["order_id"],
                    context.get("date", "")
                )
                cached = CACHE.get(cache_key, settings.cache_ttl_minutes)
                
                if cached:
                    logger.info(f"{self.name}: Using cached result")
                    findings = cached
                else:
                    findings = self._execute_tool(context, state)
                    CACHE.set(cache_key, findings)
            else:
                findings = self._execute_tool(context, state)
            
            # Reflection (conditional based on need and config)
            if self._needs_reflection(str(findings)):
                analysis = self._reflect(findings, context, state)
            else:
                analysis = self._simple_summary(findings)
            
            # Store findings efficiently
            findings["analysis"] = analysis
            self._store_findings(state, findings, context)
            
            # Add message to conversation
            state["messages"].append(AIMessage(
                content=f"**[{self.name}] {prefix}**\n\n{analysis}",
                name=self.name
            ))
            
            logger.info(f"{self.name}: Execution successful")
            
        except Exception as e:
            logger.error(f"{self.name} failed: {str(e)}", exc_info=True)
            
            error_msg = f"⚠️ {self.name} encountered an error: {str(e)}"
            
            # Log error
            if "error_log" not in state:
                state["error_log"] = []
            state["error_log"].append(f"{self.name}: {str(e)}")
            
            # Add error message
            state["messages"].append(AIMessage(
                content=f"**[{self.name}] {prefix}**\n\n{error_msg}",
                name=self.name
            ))
            
            # Store error in findings
            self._store_findings(state, {"error": str(e)}, context)
        
        return state
