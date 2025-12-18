# app/routes.py - WebSocket & HTTP Endpoints

from quart import Quart, websocket, jsonify, send_file, request
import asyncio
import json
import logging
from app.session_manager import SessionManager
from app.llm_service import LLMService
from app.database import SupabaseDB
from app.background_tasks import BackgroundTaskProcessor
from app.models import EventType

# ===== SETUP LOGGING =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== INITIALIZE APP =====
app = Quart(__name__)
app.config['PROVIDE_AUTOMATIC_OPTIONS'] = True  # Fix the error
session_manager = SessionManager()
llm_service = LLMService()


# ===== HTTP ENDPOINTS =====

@app.route("/")
async def index():
    """Serve frontend HTML"""
    try:
        return await send_file("frontend/index.html")
    except Exception as e:
        logger.error(f"Error serving index: {e}")
        return jsonify({"error": "Frontend not found"}), 404


@app.route("/health")
async def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "model": "ollama-qwen2.5:3b",
        "version": "1.0"
    }), 200


@app.route("/session/<session_id>")
async def get_session(session_id: str):
    """Retrieve session details and event log"""
    try:
        events = await SupabaseDB.get_session_events(session_id, limit=50)
        return jsonify({
            "session_id": session_id,
            "events_count": len(events),
            "events": events
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving session: {e}")
        return jsonify({"error": str(e)}), 500


# ===== WEBSOCKET ENDPOINT =====

@app.websocket("/ws/session/<session_id>")
async def ws_session(session_id: str):
    """Main WebSocket endpoint for real-time conversation"""
    user_id = request.args.get("user_id", "anonymous")
    
    try:
        logger.info(f"🔌 WebSocket connection: {session_id} from user {user_id}")
        
        # Create or retrieve session
        if not session_manager.get_session(session_id):
            session_id = await session_manager.create_session(user_id)
        
        # session = session_manager.get_session(session_id)
        
        # Send session initialization message
        await websocket.send(json.dumps({
            "type": "session_started",
            "session_id": session_id,
            "user_id": user_id,
            "model": "ollama-qwen2.5:3b",
            "message": "Session initialized. Start sending messages!"
        }))
        
        # Handle incoming messages
        await _handle_messages(session_id)
    
    except Exception as e:
        logger.error(f"✗ WebSocket error: {e}")
        try:
            await websocket.send(json.dumps({
                "type": "error",
                "error": str(e)
            }))
        except:
            pass
    
    finally:
        # Cleanup on disconnect
        await session_manager.close_session(session_id)
        await session_manager.cleanup_session(session_id)
        
        logger.info(f"🔌 Disconnected: {session_id}")
        
        # Trigger background task for summary generation
        app.add_background_task(
            BackgroundTaskProcessor.generate_session_summary, 
            session_id
        )


# ===== WEBSOCKET MESSAGE HANDLER =====

async def _handle_messages(session_id: str):
    """Handle incoming messages and stream responses"""
    session = session_manager.get_session(session_id)
    
    if not session:
        logger.error(f"Session not found: {session_id}")
        return
    
    while True:
        try:
            # Receive message from client
            data = await websocket.receive_json()
            user_message = data.get("message", "").strip()
            
            if not user_message:
                logger.debug("Empty message received, skipping")
                if session.is_expired():
                    return
                continue
            
            logger.info(f"📨 Message from user: {user_message[:50]}...")
            
            # Add user message to session & DB
            session.add_message("user", user_message)
            SupabaseDB.log_event(session_id,EventType.USER_MESSAGE,user_message)
            
            # Update Session columms
            SupabaseDB.update_session(session_id)
            
            # Detect intent and route
            intent = _detect_intent(user_message)
            session.update_intent_route(intent)
            
            # Send response start signal
            await websocket.send(json.dumps({
                "type": "response_start",
                "intent": intent,
                "model": "ollama-qwen2.5:3b"
            }))
            
            # Get conversation context
            context = session.get_conversation_context()
            full_response = ""
            
            # Stream response from Ollama
            logger.info(f"🤖 Streaming response from Ollama...")
            async for chunk in llm_service.stream_response(context, session_id):
                # Send each chunk to client
                await websocket.send(json.dumps({
                    "type": "response_chunk",
                    "chunk": chunk
                }))
                full_response += chunk
            
            # Add AI response to session
            session.add_message("assistant", full_response)
            
            # Send completion signal
            await websocket.send(json.dumps({
                "type": "response_complete",
                "message_count": len(session.messages),
                "total_exchanges": len(session.messages) // 2
            }))
            
            logger.info(f"✓ Response complete ({len(full_response)} chars)")
        
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received")
            try:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "Invalid message format"
                }))
            except:
                pass
        
        except Exception as e:
            logger.error(f"✗ Error in message handler: {e}")
            try:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": str(e)
                }))
            except:
                pass


# ===== INTENT DETECTION =====

def _detect_intent(message: str) -> str:
    """Detect user intent from message for multi-step routing"""
    message_lower = message.lower()
    
    if any(word in message_lower for word in ["weather", "temperature", "climate", "forecast", "rain", "snow"]):
        return "weather"
    
    elif any(word in message_lower for word in ["search", "find", "look up", "research", "tell me about"]):
        return "search"
    
    elif any(word in message_lower for word in ["code", "python", "javascript", "java", "program", "programming", "debug"]):
        return "technical"
    
    else:
        return "general"


# ===== ERROR HANDLERS =====

@app.errorhandler(404)
async def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
async def server_error(error):
    """Handle 500 errors"""
    logger.error(f"Server error: {error}")
    return jsonify({"error": "Internal server error"}), 500
