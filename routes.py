"""
API routes for Financial Trading Agent
Fixed to work with updated QueryParameters and date handling
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import uuid
import json

from src.api.schemas import (
    InvestigateRequest,
    InvestigateResponse,
    CompareRequest,
    CompareResponse,
    CodeAnalysisRequest,
    CodeAnalysisResponse,
    LogsRequest,
    LogsResponse,
    QueryResponse,
    JobStatus,
    StreamResponse
)
from src.api.main import get_agent_graph
from src.models.state import AgentState
from src.models.query_parameters import QueryParameters
from src.utils.date_handler import DateHandler
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job storage (use Redis in production)
jobs: Dict[str, Dict[str, Any]] = {}


def create_initial_state(query: str) -> AgentState:
    """
    Create initial agent state
    
    Note: Parameters will be filled by Supervisor Agent based on query analysis
    """
    return {
        "messages": [],
        "user_query": query,
        "parameters": QueryParameters(
            intent="Investigation",
            reasoning="Initial state - will be updated by Supervisor"
        ),
        "investigation_step": 0,
        "findings": {},
        "comparison_findings": {},
        "final_answer": "",
        "sender": "",
        "current_investigation": "primary",
        "error_log": [],
        # Enrichment fields
        "aaa_order_id": None,
        "enrichment_flow": False,
        "actual_order_id": None
    }


def format_response(result: AgentState) -> Dict[str, Any]:
    """Format agent result for API response"""
    params = result.get("parameters")
    
    agents_used = list(set(
        msg.name for msg in result.get("messages", [])
        if hasattr(msg, 'name') and msg.name and msg.name != "Supervisor"
    ))
    
    return {
        "answer": result.get("final_answer", ""),
        "intent": params.intent if params else "Unknown",
        "order_id": params.order_id if params else None,
        "date": params.date if params else None,
        "comparison_order_id": params.comparison_order_id if params else None,
        "comparison_date": params.comparison_date if params else None,
        "enriched_order_id": result.get("actual_order_id"),
        "agents_used": agents_used,
        "total_messages": len(result.get("messages", [])),
        "errors": result.get("error_log", []),
        "findings": {
            "primary": result.get("findings", {}),
            "comparison": result.get("comparison_findings", {})
        },
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# QUERY ENDPOINTS
# ============================================================================

@router.post("/query", response_model=QueryResponse)
async def query(
    query: str,
    order_id: Optional[str] = None,
    date: Optional[str] = None,
    agent = Depends(get_agent_graph)
):
    """
    Generic query endpoint - automatically routes to appropriate agents
    
    Examples:
    - "How does pricing work?" → Knowledge
    - "Show logs for order ABC123 on 2025-01-15" → Logs
    - "Investigate order XYZ789" → Investigation
    - "Investigate order D12.345.678 on 12/10/2025" → Investigation with enrichment
    """
    try:
        logger.info(f"Received query: {query}")
        
        # Build enhanced query with provided order_id and date
        enhanced_query = query
        if order_id and order_id not in query:
            enhanced_query += f" for order {order_id}"
        if date and date not in query:
            enhanced_query += f" on {date}"
        
        state = create_initial_state(enhanced_query)
        result = agent.invoke(state)
        
        response = format_response(result)
        
        return QueryResponse(
            success=True,
            query=query,
            **response
        )
        
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate(
    request: InvestigateRequest,
    agent = Depends(get_agent_graph)
):
    """
    Investigate a specific order to find pricing issues
    
    Executes: Splunk → Database → DebugAPI → Analysis
    
    Supports:
    - Standard order IDs (ORD123456)
    - D-prefix orders (D12.345.678) - automatically enriched
    - Various date formats (will be normalized to yyyy-mm-dd)
    """
    try:
        logger.info(f"Investigating order: {request.order_id}")
        
        # Build query string - Supervisor will parse and normalize
        query = f"Investigate order {request.order_id}"
        if request.date:
            query += f" on {request.date}"  # Date will be normalized by QueryParameters
        if request.reason:
            query += f" - {request.reason}"
        
        state = create_initial_state(query)
        result = agent.invoke(state)
        
        response = format_response(result)
        
        return InvestigateResponse(
            success=True,
            order_id=request.order_id,
            date=request.date,
            **response
        )
        
    except Exception as e:
        logger.error(f"Investigation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare", response_model=CompareResponse)
async def compare_orders(
    request: CompareRequest,
    agent = Depends(get_agent_graph)
):
    """
    Compare two orders to find pricing differences
    
    Executes both investigations in parallel, then performs comparison
    
    Supports:
    - Mix of standard and D-prefix orders
    - Different dates for each order
    - Automatic date normalization
    """
    try:
        logger.info(f"Comparing orders: {request.primary_order_id} vs {request.comparison_order_id}")
        
        # Build comparison query - Supervisor will handle date normalization
        query = f"Compare order {request.primary_order_id}"
        if request.primary_date:
            query += f" from {request.primary_date}"
        query += f" with order {request.comparison_order_id}"
        if request.comparison_date:
            query += f" from {request.comparison_date}"
        if request.reason:
            query += f" - {request.reason}"
        
        state = create_initial_state(query)
        result = agent.invoke(state)
        
        response = format_response(result)
        
        return CompareResponse(
            success=True,
            primary_order_id=request.primary_order_id,
            comparison_order_id=request.comparison_order_id,
            differences=response.get("answer", ""),
            **response
        )
        
    except Exception as e:
        logger.error(f"Comparison failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/code/analyze", response_model=CodeAnalysisResponse)
async def analyze_code(
    request: CodeAnalysisRequest,
    agent = Depends(get_agent_graph)
):
    """
    Analyze Java/Spring code
    
    Can explain implementations, trace execution, show configurations
    """
    try:
        logger.info(f"Code analysis: {request.query}")
        
        query = request.query
        if request.order_id:
            query += f" for order {request.order_id}"
        if request.class_name:
            query += f" in class {request.class_name}"
        if request.method_name:
            query += f" method {request.method_name}"
        
        state = create_initial_state(query)
        result = agent.invoke(state)
        
        response = format_response(result)
        
        return CodeAnalysisResponse(
            success=True,
            query=request.query,
            **response
        )
        
    except Exception as e:
        logger.error(f"Code analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs", response_model=LogsResponse)
async def get_logs(
    request: LogsRequest,
    agent = Depends(get_agent_graph)
):
    """
    Retrieve and analyze logs for specific order
    
    Supports:
    - Standard and D-prefix orders
    - Various date formats
    """
    try:
        logger.info(f"Fetching logs for: {request.order_id}")
        
        query = f"Show me logs for order {request.order_id}"
        if request.date:
            query += f" on {request.date}"  # Will be normalized
        
        state = create_initial_state(query)
        result = agent.invoke(state)
        
        response = format_response(result)
        
        return LogsResponse(
            success=True,
            order_id=request.order_id,
            date=request.date,
            **response
        )
        
    except Exception as e:
        logger.error(f"Log retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ASYNC/BACKGROUND JOB ENDPOINTS
# ============================================================================

@router.post("/investigate/async")
async def investigate_async(
    request: InvestigateRequest,
    background_tasks: BackgroundTasks,
    agent = Depends(get_agent_graph)
):
    """
    Start investigation as background job
    Returns job_id to check status later
    """
    job_id = str(uuid.uuid4())
    
    jobs[job_id] = {
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "request": request.dict(),
        "result": None,
        "error": None
    }
    
    async def run_investigation():
        try:
            jobs[job_id]["status"] = "running"
            jobs[job_id]["started_at"] = datetime.now().isoformat()
            
            query = f"Investigate order {request.order_id}"
            if request.date:
                query += f" on {request.date}"
            if request.reason:
                query += f" - {request.reason}"
            
            state = create_initial_state(query)
            result = agent.invoke(state)
            
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            jobs[job_id]["result"] = format_response(result)
            
        except Exception as e:
            logger.error(f"Background investigation failed: {e}", exc_info=True)
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["failed_at"] = datetime.now().isoformat()
    
    background_tasks.add_task(run_investigation)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Investigation started in background",
        "status_url": f"/api/v1/jobs/{job_id}"
    }


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Check status of background job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        result=job.get("result"),
        error=job.get("error")
    )


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@router.get("/monitoring/health")
async def monitoring_health(agent = Depends(get_agent_graph)):
    """Get system health from monitoring agent"""
    try:
        query = "What's the current health of the pricing service?"
        state = create_initial_state(query)
        result = agent.invoke(state)
        
        return {
            "status": "healthy",
            "metrics": result.get("final_answer", ""),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# STREAMING ENDPOINT (Advanced)
# ============================================================================

@router.post("/query/stream")
async def query_stream(
    query: str,
    order_id: Optional[str] = None,
    date: Optional[str] = None,
    agent = Depends(get_agent_graph)
):
    """
    Stream agent responses in real-time (Server-Sent Events)
    """
    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'start', 'message': 'Investigation started'})}\n\n"
            
            enhanced_query = query
            if order_id:
                enhanced_query += f" for order {order_id}"
            if date:
                enhanced_query += f" on {date}"
            
            state = create_initial_state(enhanced_query)
            
            # TODO: Implement streaming from LangGraph
            # This is a placeholder - actual streaming requires LangGraph stream support
            result = agent.invoke(state)
            
            # Stream each agent's output
            for msg in result.get("messages", []):
                if hasattr(msg, 'name') and msg.name:
                    event = {
                        "type": "agent_message",
                        "agent": msg.name,
                        "content": msg.content[:200]  # Truncate for streaming
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                    await asyncio.sleep(0.1)  # Small delay
            
            # Final result
            final_event = {
                "type": "complete",
                "answer": result.get("final_answer", ""),
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(final_event)}\n\n"
            
        except Exception as e:
            error_event = {
                "type": "error",
                "error": str(e)
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/agents")
async def list_agents():
    """List all available agents"""
    return {
        "agents": [
            {
                "name": "Order_Enricher_Agent",
                "purpose": "D-prefix order ID enrichment",
                "use_case": "Automatically enriches D12.345.678 to actual order ID",
                "trigger": "Order starts with D and has 9 characters"
            },
            {
                "name": "VectorDB_Agent",
                "purpose": "Knowledge & documentation retrieval",
                "use_case": "How does pricing work?"
            },
            {
                "name": "Splunk_Agent",
                "purpose": "Log analysis & forensics",
                "use_case": "Show logs for order ABC123"
            },
            {
                "name": "Database_Agent",
                "purpose": "Oracle DB queries & configuration",
                "use_case": "Get order details, enrich D-prefix orders"
            },
            {
                "name": "DebugAPI_Agent",
                "purpose": "Order simulation & testing",
                "use_case": "Simulate pricing calculation"
            },
            {
                "name": "Monitoring_Agent",
                "purpose": "System health & metrics",
                "use_case": "System health status"
            },
            {
                "name": "Code_Agent",
                "purpose": "Java/Spring code analysis",
                "use_case": "Explain pricing code"
            },
            {
                "name": "Comparison_Agent",
                "purpose": "Side-by-side order comparison",
                "use_case": "Compare two orders"
            },
            {
                "name": "Summarization_Agent",
                "purpose": "LLM-powered comprehensive summaries",
                "use_case": "Generate executive-ready investigation reports"
            }
        ]
    }


@router.get("/date/normalize")
async def normalize_date(date_input: str):
    """
    Normalize a date string to yyyy-mm-dd format
    
    Useful for testing date normalization before sending queries
    """
    try:
        normalized = DateHandler.normalize_date(date_input)
        return {
            "input": date_input,
            "normalized": normalized,
            "current_date": DateHandler.get_current_date(),
            "is_valid": DateHandler.validate_date(normalized)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Date normalization failed: {str(e)}")


@router.get("/date/current")
async def get_current_date():
    """Get current date in yyyy-mm-dd format"""
    return {
        "current_date": DateHandler.get_current_date(),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/examples")
async def get_query_examples():
    """Get example queries for different use cases"""
    return {
        "examples": {
            "knowledge": [
                "How does client pricing work for GOLD tier clients?",
                "Explain the pricing calculation algorithm"
            ],
            "investigation": [
                "Investigate order ABC123 from 2025-01-15",
                "Investigate order D12.345.678 on 12/10/2025",
                "Why did order XYZ789 fail?",
                "Show me what happened to order ABC123 yesterday"
            ],
            "logs": [
                "Show me logs for order ABC123 on 2025-01-15",
                "Get logs for order D11111111",
                "Show system logs from yesterday"
            ],
            "comparison": [
                "Compare order ABC123 with DEF456",
                "Compare order D11111111 from yesterday with ORD222222",
                "Why do orders ABC123 and XYZ789 have different prices?",
                "Compare pricing for ABC123 on 2025-01-10 vs 2025-01-15"
            ],
            "code_analysis": [
                "How does the pricing calculation work in the Java code?",
                "Show me the PricingEngine implementation",
                "Explain tier discount logic in the code"
            ],
            "monitoring": [
                "What's the current health of the pricing service?",
                "Show system metrics",
                "Check service status"
            ],
            "enrichment": [
                "Investigate order D12.345.678",
                "Compare D11111111 with D22222222",
                "Show logs for D99999999 on 2025-10-12"
            ],
            "date_formats": [
                "Investigate order ABC123 on 2025-10-12",
                "Investigate order ABC123 on 12/10/2025",
                "Investigate order ABC123 on 12-10-2025",
                "Investigate order ABC123 from yesterday",
                "Investigate order ABC123 from today"
            ]
        }
    }


@router.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "Financial Trading Agent API",
        "version": "2.0.0",
        "features": {
            "order_enrichment": True,
            "date_normalization": True,
            "llm_summarization": True,
            "comparison": True,
            "code_analysis": True
        },
        "timestamp": datetime.now().isoformat()
    }


@router.get("/")
async def api_root():
    """API root with documentation links"""
    return {
        "message": "Financial Trading Agent API",
        "version": "2.0.0",
        "documentation": "/docs",
        "endpoints": {
            "query": "/api/v1/query",
            "investigate": "/api/v1/investigate",
            "compare": "/api/v1/compare",
            "logs": "/api/v1/logs",
            "code_analysis": "/api/v1/code/analyze",
            "health": "/api/v1/health",
            "agents": "/api/v1/agents",
            "examples": "/api/v1/examples",
            "date_normalize": "/api/v1/date/normalize"
        },
        "features": [
            "Automatic D-prefix order enrichment",
            "Multi-format date normalization",
            "LLM-powered summaries",
            "Side-by-side order comparison",
            "Code analysis",
            "Real-time log analysis"
        ]
    }
