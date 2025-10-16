"""
FastAPI endpoints for intelligent chatbot with LLM-based routing
Supports conversation memory, context management, and smart intent detection
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import logging

from src.chatbot.intelligent_chatbot import InvestigationChatbot

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory session storage (use Redis in production)
chat_sessions: Dict[str, InvestigationChatbot] = {}

# Session timeout (in seconds) - 1 hour
SESSION_TIMEOUT = 3600


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(..., description="User's message/query")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class IntentInfo(BaseModel):
    """Intent classification information"""
    action_type: str
    confidence: float
    reasoning: str
    requires_context: bool
    extracted_entities: Dict[str, Optional[str]]


class ChatResponse(BaseModel):
    """Chat response model"""
    session_id: str
    message: str
    response: str
    response_type: str  # "investigation", "context_answer", "single_agent", etc.
    intent: Optional[IntentInfo] = None
    timestamp: str
    duration_seconds: float
    context_available: bool


class SessionInfo(BaseModel):
    """Session information"""
    session_id: str
    created_at: str
    last_activity: str
    message_count: int
    investigation_count: int
    current_context: Optional[Dict] = None
    context_available: bool


class SessionList(BaseModel):
    """List of active sessions"""
    sessions: List[Dict]
    total: int


class StatusResponse(BaseModel):
    """Generic status response"""
    message: str
    session_id: str
    timestamp: str


def cleanup_expired_sessions():
    """Remove expired sessions (optional background task)"""
    current_time = datetime.now()
    expired = []
    
    for session_id, chatbot in chat_sessions.items():
        if chatbot.conversation_history:
            last_activity = chatbot.conversation_history[-1].get("timestamp")
            if last_activity:
                last_time = datetime.fromisoformat(last_activity)
                if (current_time - last_time).total_seconds() > SESSION_TIMEOUT:
                    expired.append(session_id)
    
    for session_id in expired:
        del chat_sessions[session_id]
        logger.info(f"Cleaned up expired session: {session_id}")


def get_or_create_session(session_id: Optional[str] = None) -> tuple[str, InvestigationChatbot]:
    """Get existing session or create new one"""
    if session_id and session_id in chat_sessions:
        logger.info(f"Resuming session: {session_id}")
        return session_id, chat_sessions[session_id]
    
    # Create new session
    new_session_id = str(uuid.uuid4())
    chatbot = InvestigationChatbot()
    chat_sessions[new_session_id] = chatbot
    
    logger.info(f"Created new session: {new_session_id}")
    return new_session_id, chatbot


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Intelligent chat endpoint with LLM-based routing
    
    The chatbot will automatically determine the appropriate action:
    - Answer from previous investigation context
    - Start new investigation
    - Call specific agent (Knowledge, Code, Debug API, Monitoring)
    - Request clarification
    - Decline re-investigation of same order
    
    Example usage:
    ```python
    # First message (investigation)
    response1 = requests.post("/api/v1/chat", json={
        "message": "Investigate order D12345678"
    })
    session_id = response1.json()["session_id"]
    
    # Follow-up question (uses context)
    response2 = requests.post("/api/v1/chat", json={
        "message": "Why did it fail?",
        "session_id": session_id
    })
    
    # Knowledge query (calls Knowledge Agent)
    response3 = requests.post("/api/v1/chat", json={
        "message": "How does FX pricing work?",
        "session_id": session_id
    })
    
    # Code analysis (calls Code Agent)
    response4 = requests.post("/api/v1/chat", json={
        "message": "Show me the spread calculation code",
        "session_id": session_id
    })
    ```
    """
    start_time = datetime.now()
    
    try:
        # Get or create session
        session_id, chatbot = get_or_create_session(request.session_id)
        
        # Classify query first (for response metadata)
        intent = chatbot.classify_query(request.message)
        
        # Process message with intelligent routing
        response = chatbot.chat(request.message)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        # Determine response type from last history entry
        response_type = "unknown"
        if chatbot.conversation_history:
            last_entry = chatbot.conversation_history[-1]
            if "investigation_response" in last_entry.get("type", ""):
                response_type = "investigation"
            elif "context_answer_response" in last_entry.get("type", ""):
                response_type = "context_answer"
            elif "single_agent_response" in last_entry.get("type", ""):
                response_type = "single_agent"
            elif "clarification_response" in last_entry.get("type", ""):
                response_type = "clarification"
            elif "decline_response" in last_entry.get("type", ""):
                response_type = "decline"
        
        return ChatResponse(
            session_id=session_id,
            message=request.message,
            response=response,
            response_type=response_type,
            intent=IntentInfo(
                action_type=intent.action_type,
                confidence=intent.confidence,
                reasoning=intent.reasoning,
                requires_context=intent.requires_context,
                extracted_entities=intent.extracted_entities
            ),
            timestamp=datetime.now().isoformat(),
            duration_seconds=round(duration, 2),
            context_available=bool(chatbot.investigation_context)
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/session/{session_id}", response_model=SessionInfo)
async def get_session_info(session_id: str):
    """
    Get detailed information about a chat session
    
    Returns session metadata, message counts, and current investigation context
    """
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    chatbot = chat_sessions[session_id]
    
    # Count different message types
    investigation_count = sum(
        1 for h in chatbot.conversation_history 
        if h.get("type") == "investigation"
    )
    
    message_count = sum(
        1 for h in chatbot.conversation_history 
        if h.get("type") == "user_query"
    )
    
    # Get timestamps
    created_at = (
        chatbot.conversation_history[0]["timestamp"] 
        if chatbot.conversation_history 
        else datetime.now().isoformat()
    )
    
    last_activity = (
        chatbot.conversation_history[-1]["timestamp"] 
        if chatbot.conversation_history 
        else datetime.now().isoformat()
    )
    
    return SessionInfo(
        session_id=session_id,
        created_at=created_at,
        last_activity=last_activity,
        message_count=message_count,
        investigation_count=investigation_count,
        current_context=chatbot.investigation_context if chatbot.investigation_context else None,
        context_available=bool(chatbot.investigation_context)
    )


@router.delete("/chat/session/{session_id}", response_model=StatusResponse)
async def delete_session(session_id: str):
    """
    Delete a chat session and free up resources
    
    Use this to clean up sessions when users are done
    """
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del chat_sessions[session_id]
    logger.info(f"Deleted session: {session_id}")
    
    return StatusResponse(
        message="Session deleted successfully",
        session_id=session_id,
        timestamp=datetime.now().isoformat()
    )


@router.post("/chat/session/{session_id}/clear", response_model=StatusResponse)
async def clear_session_context(session_id: str):
    """
    Clear investigation context for a session
    
    Useful when user wants to start a fresh investigation
    without losing the entire session history
    """
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    chatbot = chat_sessions[session_id]
    chatbot.clear_context()
    
    logger.info(f"Cleared context for session: {session_id}")
    
    return StatusResponse(
        message="Context cleared successfully",
        session_id=session_id,
        timestamp=datetime.now().isoformat()
    )


@router.get("/chat/sessions", response_model=SessionList)
async def list_sessions():
    """
    List all active chat sessions
    
    Returns summary information for each session
    """
    cleanup_expired_sessions()  # Clean up old sessions first
    
    sessions = []
    for session_id, chatbot in chat_sessions.items():
        message_count = sum(
            1 for h in chatbot.conversation_history 
            if h.get("type") == "user_query"
        )
        
        investigation_count = sum(
            1 for h in chatbot.conversation_history 
            if h.get("type") == "investigation"
        )
        
        last_activity = (
            chatbot.conversation_history[-1]["timestamp"] 
            if chatbot.conversation_history 
            else None
        )
        
        sessions.append({
            "session_id": session_id,
            "message_count": message_count,
            "investigation_count": investigation_count,
            "last_activity": last_activity,
            "context_available": bool(chatbot.investigation_context),
            "current_order": chatbot.investigation_context.get("order_id") if chatbot.investigation_context else None
        })
    
    return SessionList(
        sessions=sessions,
        total=len(sessions)
    )


@router.get("/chat/session/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: Optional[int] = 10,
    include_responses: bool = True
):
    """
    Get conversation history for a session
    
    Args:
        session_id: Session identifier
        limit: Maximum number of entries to return (default: 10)
        include_responses: Include bot responses in history (default: True)
    
    Returns:
        List of conversation history entries
    """
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    chatbot = chat_sessions[session_id]
    history = chatbot.conversation_history
    
    # Filter if needed
    if not include_responses:
        history = [h for h in history if h.get("type") == "user_query"]
    
    # Apply limit
    history = history[-limit:] if limit else history
    
    # Remove sensitive data (like full result objects)
    clean_history = []
    for entry in history:
        clean_entry = {
            "type": entry.get("type"),
            "timestamp": entry.get("timestamp"),
        }
        
        if "query" in entry:
            clean_entry["query"] = entry["query"]
        
        if "answer" in entry:
            clean_entry["answer"] = entry["answer"]
        
        if "intent_classification" in entry:
            intent = entry["intent_classification"]
            clean_entry["intent"] = {
                "action_type": intent.get("action_type"),
                "confidence": intent.get("confidence"),
                "reasoning": intent.get("reasoning")
            }
        
        clean_history.append(clean_entry)
    
    return {
        "session_id": session_id,
        "history": clean_history,
        "total_entries": len(clean_history)
    }


@router.post("/chat/session/{session_id}/context/update")
async def update_session_context(
    session_id: str,
    context: Dict[str, str]
):
    """
    Manually update investigation context for a session
    
    Advanced feature - allows external systems to inject context
    
    Args:
        session_id: Session identifier
        context: Context data to merge (e.g., {"order_id": "D12345678"})
    """
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    chatbot = chat_sessions[session_id]
    
    # Merge with existing context
    if chatbot.investigation_context:
        chatbot.investigation_context.update(context)
    else:
        chatbot.investigation_context = context
    
    logger.info(f"Updated context for session {session_id}: {context}")
    
    return StatusResponse(
        message="Context updated successfully",
        session_id=session_id,
        timestamp=datetime.now().isoformat()
    )


@router.post("/chat/classify")
async def classify_query_endpoint(
    message: str,
    session_id: Optional[str] = None
):
    """
    Classify a query without executing it
    
    Useful for previewing what action the chatbot would take
    without actually running the investigation/agent
    
    Args:
        message: Query to classify
        session_id: Optional session for context-aware classification
    
    Returns:
        Intent classification with confidence and reasoning
    """
    try:
        # Get or create temporary chatbot
        if session_id and session_id in chat_sessions:
            chatbot = chat_sessions[session_id]
        else:
            # Create temporary chatbot for classification
            chatbot = InvestigationChatbot()
        
        intent = chatbot.classify_query(message)
        
        return {
            "message": message,
            "classification": {
                "action_type": intent.action_type,
                "confidence": intent.confidence,
                "reasoning": intent.reasoning,
                "requires_context": intent.requires_context,
                "extracted_entities": intent.extracted_entities,
                "suggested_response": intent.suggested_response
            },
            "context_available": bool(chatbot.investigation_context),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Classification error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Health check endpoint
    
    Returns system status and session statistics
    """
    cleanup_expired_sessions()
    
    return {
        "status": "healthy",
        "active_sessions": len(chat_sessions),
        "timestamp": datetime.now().isoformat()
    }


# Optional: WebSocket support for real-time chat
from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time chat
    
    Provides streaming responses and lower latency
    """
    await websocket.accept()
    
    try:
        # Get or create session
        _, chatbot = get_or_create_session(session_id)
        
        await websocket.send_json({
            "type": "connection",
            "message": "Connected to intelligent chatbot",
            "session_id": session_id
        })
        
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            if not message:
                continue
            
            # Classify and process
            start_time = datetime.now()
            
            try:
                intent = chatbot.classify_query(message)
                
                # Send intent classification
                await websocket.send_json({
                    "type": "intent",
                    "action_type": intent.action_type,
                    "confidence": intent.confidence,
                    "reasoning": intent.reasoning
                })
                
                # Process message
                response = chatbot.chat(message)
                duration = (datetime.now() - start_time).total_seconds()
                
                # Send response
                await websocket.send_json({
                    "type": "response",
                    "message": message,
                    "response": response,
                    "duration_seconds": round(duration, 2),
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
        await websocket.close()
