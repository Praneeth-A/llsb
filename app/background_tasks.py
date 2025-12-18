# app/background_tasks.py - Post-Session Processing

from app.llm_service import LLMService
from app.database import SupabaseDB
from app.models import EventType
import logging
import httpx
import json
logger = logging.getLogger(__name__)


class BackgroundTaskProcessor:
    """Process tasks after session ends"""
    
    @staticmethod
    async def generate_session_summary(session_id: str):
        """Generate AI summary from event log using Ollama"""
        try:
            logger.info(f"📊 Generating summary for session: {session_id}")
            
            # Retrieve event log from database
            events = await SupabaseDB.get_session_events(session_id)
            if not events:
                logger.warning(f"⚠️ No events found for session {session_id}")
                return
            
            # Build conversation text from events
            conversation_text = ""
            message_count = 0
            
            for event in events:
                event_type = event.get("event_type")
                content = event.get("content", {})
                
                if event_type == "user_message":
                    conversation_text += f"User: {content.get('content', '')}\n"
                    message_count += 1
                elif event_type == "function_call":
                    func_name = content.get("function", "unknown")
                    conversation_text += f"[Tool called: {func_name}]\n"
                elif event_type == "tool_result":
                    result = content.get("result", "unknown")
                    conversation_text += f"[Tool result: {result}]\n"
                elif event_type == "ai_response":
                    conversation_text += f"Assistant: {content.get('content', '')}\n"
                
            if not conversation_text.strip():
                logger.warning(f"⚠️ No messages to summarize for session {session_id}")
                return
            
            # Use Ollama to generate summary
            llm = LLMService()
            summary_messages = [{
                "role": "user",
                "content": f"""Summarize this conversation in 2-3 sentences. Focus on the main topics discussed and key outcomes.

Conversation:
{conversation_text[:3000]}

Summary:"""
            }]
            
            summary = ""
            logger.info(f"🤖 Calling Ollama for summary generation...")
            
            payload = {
                    "model": llm.model,
                    "messages": summary_messages,
                    "stream": True,
                    "options": {"temperature": 0.7}  
                }
            
            try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        async with client.stream("POST", f"{llm.url}/api/chat", json=payload) as response:
                            if response.status_code != 200:
                                yield f"❌ Ollama error: {response.status_code}"
                                return
                            
                            async for line in response.aiter_lines():
                                if not line: continue
                                
                                chunk_data = json.loads(line)
                                if "message" in chunk_data and chunk_data["message"].get("content"):
                                    content = chunk_data["message"]["content"]
                                    summary += content
                                    # yield content
                                
                                if chunk_data.get("done", False):
                                    break
            
            except httpx.ConnectError:
                error_msg = f"✗ Cannot connect to Ollama at {llm.url}. Is Ollama running? (ollama serve)"
                logger.error(error_msg)
                yield f"\n\n❌ ERROR: {error_msg}"
        
            except Exception as e:
                error_msg = f"❌ LLM error: {str(e)}"
                logger.error(error_msg)
                yield error_msg
            async for chunk in llm.stream_response(summary_messages, session_id):
                summary += chunk
            
            # Trim summary if too long
            summary = summary.strip()[:500]
            
            # Update database with summary
            await SupabaseDB.update_session_summary(session_id, summary)
            logger.info(f"✓ Summary generated and saved: {session_id}")
            logger.info(f"  Summary preview: {summary[:100]}...")
            
        except Exception as e:
            logger.error(f"✗ Error generating summary: {e}")
            # Continue gracefully - don't crash if summary generation fails
