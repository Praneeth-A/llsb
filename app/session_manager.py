# app/session_manager.py - WebSocket Session State Management

import uuid
from typing import Dict, List, Optional, Set
from datetime import datetime
from app.models import EventType
from app.database import SupabaseDB
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages active WebSocket sessions and conversation state"""
    
    def __init__(self):
        self.active_sessions: Dict[str, "Session"] = {}
        self.user_sessions: Dict[str, Set[str]] = {}  # user_id -> session_ids
    
    async def create_session(self, user_id: str) -> str:
        """Create new session and store in memory and database"""
        session_id = str(uuid.uuid4())
        
        try:
            # Create in database
            await SupabaseDB.create_session(user_id, session_id)
            
            # Create in memory
            session = Session(session_id, user_id)
            self.active_sessions[session_id] = session
            
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = set()
            self.user_sessions[user_id].add(session_id)
            
            logger.info(f"📝 Session created: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"✗ Error creating session: {e}")
            raise
    
    def get_session(self, session_id: str) -> Optional["Session"]:
        """Retrieve session object from memory"""
        return self.active_sessions.get(session_id)
    
    async def add_message(self, session_id: str, role: str, content: str):
        """Add message to conversation history"""
        session = self.get_session(session_id)
        if session:
            session.add_message(role, content)
            await SupabaseDB.log_event(
                session_id,
                EventType.USER_MESSAGE if role == "user" else EventType.AI_RESPONSE,
                {"role": role, "content": content}
            )
    
    async def close_session(self, session_id: str):
        """Mark session as closed"""
        session = self.get_session(session_id)
        if session:
            session.end_time = datetime.utcnow()
            logger.info(f"🔌 Session closed: {session_id}")
    
    async def cleanup_session(self, session_id: str):
        """Remove session from memory"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            if session.user_id in self.user_sessions:
                self.user_sessions[session.user_id].discard(session_id)
            del self.active_sessions[session_id]
            logger.info(f"🗑️ Session cleaned up: {session_id}")
    
    async def get_user_sessions(self, user_id: str) -> List[str]:
        """Get all active sessions for a user"""
        return list(self.user_sessions.get(user_id, set()))


class Session:
    """Individual session state management"""
    
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.messages: List[Dict[str, str]] = []
        self.intent_route = "general"  # For multi-step routing
    
    def add_message(self, role: str, content: str):
        """Add message to conversation history"""
        self.messages.append({"role": role, "content": content})
    
    def get_conversation_context(self, max_messages: int = 10) -> List[Dict[str, str]]:
        """Get last N messages for context (for LLM)"""
        return self.messages[-max_messages:]
    
    def update_intent_route(self, intent: str):
        """Update conversation route based on detected intent"""
        self.intent_route = intent
        logger.debug(f"🧭 Intent route updated: {intent}")
    
    def is_expired(self, timeout_seconds: int = 1800) -> bool:
        """Check if session has expired"""
        elapsed = (datetime.utcnow() - self.created_at).total_seconds()
        return elapsed > timeout_seconds
