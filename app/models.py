# app/models.py - Pydantic Validation Models

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# ===== ENUMS =====
class EventType(str, Enum):
    """Types of events logged in session_events table"""
    USER_MESSAGE = "user_message"
    AI_RESPONSE = "ai_response"
    FUNCTION_CALL = "function_call"
    TOOL_RESULT = "tool_result"


# ===== REQUEST MODELS =====
class UserMessage(BaseModel):
    """Validate incoming user message"""
    content: str = Field(..., min_length=1, max_length=10000)
    session_id: str


# ===== RESPONSE MODELS =====
class AIResponseChunk(BaseModel):
    """Structure for streaming LLM response chunk"""
    chunk: str
    is_complete: bool = False
    tool_calls: Optional[List[Dict[str, Any]]] = None


class FunctionCall(BaseModel):
    """Structure for function call from LLM"""
    id: str
    function_name: str
    arguments: Dict[str, Any]


class SessionMetadata(BaseModel):
    """Session metadata structure"""
    session_id: str
    user_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    summary: Optional[str] = None
    message_count: int = 0


class EventLog(BaseModel):
    """Individual event log entry"""
    session_id: str
    event_type: EventType
    content: Dict[str, Any]
    timestamp: datetime


class ToolResult(BaseModel):
    """Result from tool/function execution"""
    tool_name: str
    result: Dict[str, Any]
    error: Optional[str] = None