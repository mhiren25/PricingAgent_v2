"""
FastAPI endpoints for chatbot with conversation memory
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import uuid

# Import the chatbot class (assuming it's in a separate file)
# from src.chatbot.investigation_chatbot import InvestigationChatbot

router = APIRouter()

# In-memory session storage (use Redis in production)
chat_sessions: Dict[str, "InvestigationChatbot"] = {}


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    session_id: str
    message: str
    response: str
    response_type: str  # "investigation" or "followup"
    timestamp: str
    context: Optional[Dict] = None


class SessionInfo(BaseModel):
    """Session information"""
    session_id: str
    created_at: str
    last_activity: str
    message_count: int
    current_context: Optional[Dict] = None


def get_or_create_session(session_id: Optional[str] = None) -> tuple[str, "InvestigationChatbot"]:
    """Get existing session or create new one"""
    if session_id and session_id in chat_sessions:
        return session_id, chat_sessions[session_id]
    
    # Create new session
    new_session_id = str(uuid.uuid4())
    # chatbot = InvestigationChatbot()  # Uncomment when class is imported
    # chat_sessions[new_session_id] = chatbot
    
    return new_session_id, None  # Replace with actual chatbot


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with conversation memory
    
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
    ```
    """
    try:
        # Get or create session
        session_id, chatbot = get_or_create_session(request.session_id)
        
        if not chatbot:
            raise HTTPException(status_code=500, detail="Failed to initialize chatbot")
        
        # Determine response type
        is_followup = chatbot.is_followup_question(request.message)
        response_type = "followup" if is_followup else "investigation"
        
        # Process message
        response = chatbot.chat(request.message)
        
        return ChatResponse(
            session_id=session_id,
            message=request.message,
            response=response,
            response_type=response_type,
            timestamp=datetime.now().isoformat(),
            context=chatbot.investigation_context if chatbot.investigation_context else None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/session/{session_id}", response_model=SessionInfo)
async def get_session_info(session_id: str):
    """Get information about a chat session"""
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    chatbot = chat_sessions[session_id]
    
    return SessionInfo(
        session_id=session_id,
        created_at=chatbot.conversation_history[0]["timestamp"] if chatbot.conversation_history else datetime.now().isoformat(),
        last_activity=chatbot.conversation_history[-1]["timestamp"] if chatbot.conversation_history else datetime.now().isoformat(),
        message_count=len([h for h in chatbot.conversation_history if h["type"] == "user_query"]),
        current_context=chatbot.investigation_context if chatbot.investigation_context else None
    )


@router.delete("/chat/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session"""
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del chat_sessions[session_id]
    
    return {"message": "Session deleted", "session_id": session_id}


@router.post("/chat/session/{session_id}/clear")
async def clear_session_context(session_id: str):
    """Clear investigation context for a session"""
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    chatbot = chat_sessions[session_id]
    chatbot.clear_context()
    
    return {"message": "Context cleared", "session_id": session_id}


@router.get("/chat/sessions")
async def list_sessions():
    """List all active chat sessions"""
    sessions = []
    for session_id, chatbot in chat_sessions.items():
        sessions.append({
            "session_id": session_id,
            "message_count": len([h for h in chatbot.conversation_history if h["type"] == "user_query"]),
            "last_activity": chatbot.conversation_history[-1]["timestamp"] if chatbot.conversation_history else None,
            "has_context": bool(chatbot.investigation_context)
        })
    
    return {"sessions": sessions, "total": len(sessions)}
