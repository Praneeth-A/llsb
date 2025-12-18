# app/database.py - Supabase Async Client Wrapper

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from supabase import AsyncClient, acreate_client
from app.config import Config
from app.models import EventType
import logging

logger = logging.getLogger(__name__)


class SupabaseDB:
    """Async Supabase database wrapper for session and event management"""
    
    _instance: Optional[AsyncClient] = None
    
    @classmethod
    async def get_client(cls) -> AsyncClient:
        """Get or create async Supabase client (singleton pattern)"""
        if cls._instance is None:
            cls._instance = await acreate_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        return cls._instance
    
    @staticmethod
    async def create_session(user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Create new session record in database"""
        try:
            client = await SupabaseDB.get_client()
            response = await client.table("sessions").insert({
                "user_id": user_id,
                "session_id": session_id,
                "start_time": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()               
            }).execute()
            logger.info(f"✓ Session created: {session_id}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"✗ Error creating session: {e}")
            raise
    
    @staticmethod
    async def log_event(session_id: str, event_type: EventType, content: Dict[str, Any]):
        """Log event to session_events table"""
        try:
            client = await SupabaseDB.get_client()
            await client.table("session_events").insert({
                "session_id": session_id,
                "event_type": event_type.value,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"✗ Error logging event: {e}")
            raise
    
    @staticmethod
    async def get_session_events(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve events for a session from database"""
        try:
            client = await SupabaseDB.get_client()
            response = await client.table("session_events")\
                .select("*")\
                .eq("session_id", session_id)\
                .order("timestamp", desc=False)\
                .limit(limit)\
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"✗ Error retrieving events: {e}")
            return []
    
    @staticmethod
    async def update_session_summary(session_id: str, summary: str = None):
        """Update session with AI-generated summary and end time"""
        try:
            client = await SupabaseDB.get_client()
            now = datetime.utcnow()
            
            # Get session start time to calculate duration
            session_data = await client.table("sessions")\
                .select("start_time")\
                .eq("session_id", session_id)\
                .execute()
            
            
            if session_data.data:
                start_time = datetime.fromisoformat(session_data.data[0]["start_time"])
                duration = int((now - start_time).total_seconds())
                if summary is None:
                  message_count=int(session_data.data["message_count"])+1 
                else:
                  end_time = now.isoformat() 
            
                await client.table("sessions").update({
                    "summary": summary,
                    "end_time": end_time,
                    "updated_at": now.isoformat(), #
                    "duration_seconds": duration,
                    "message_count": message_count
                }).eq("session_id", session_id).execute()
            
            logger.info(f"✓ Session summary updated: {session_id}")
        except Exception as e:
            logger.error(f"✗ Error updating session summary: {e}")
            raise
   
    @classmethod
    async def update_session(cls, session_id: str):
        """Update session with Latest message info"""
        cls.update_session_summary(session_id)
        
    @staticmethod
    async def close():
        """Close database connection"""
        if SupabaseDB._instance:
            await SupabaseDB._instance.close()
            logger.info("✓ Database connection closed")
