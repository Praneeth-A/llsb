# app/llm_service.py - Ollama Streaming Service (COMPLETELY FREE)

import httpx
import json
from typing import AsyncGenerator, List, Dict, Any, Optional
from app.config import Config
from app.database import SupabaseDB
from app.models import EventType
import logging

logger = logging.getLogger(__name__)

class LLMService:
    """Ollama qwen2.5:3b with NATIVE tool calling"""
    
    def __init__(self):
        self.url = Config.OLLAMA_URL
        self.model = Config.OLLAMA_MODEL  # qwen2.5:3b
        self.tools = self._define_tools()
    
    def _define_tools(self) -> List[Dict[str, Any]]:
        """OpenAI-style tool definitions for qwen2.5"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name, e.g. 'London', 'New York'"
                            }
                        },
                        "required": ["location"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Search internal knowledge base",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
    
    async def stream_response(
        self, 
        messages: List[Dict[str, str]], 
        session_id: str
    ) -> AsyncGenerator[str, None]:
        """Stream + Native tool calling loop"""
        full_response = ""
        
        # Tool-aware system prompt
        tool_prompt = "You have access to tools. Use them when needed. Respond naturally."
        ollama_messages = [{"role": "system", "content": tool_prompt}, *messages]
        
        # try:
        logger.info(f"🤖 Calling Ollama tools: {self.url}/api/chat")
            
            # async with httpx.AsyncClient() as client:
                # STEP 1: Check for tool calls & execute
        await self._handle_tool_calls(ollama_messages, session_id)
        
        
    
    async def _handle_tool_calls(self, messages: List[Dict], session_id: str):
        """Execute tool calls and continue conversation"""
        try:  
        
           async with httpx.AsyncClient() as client:
            # Get final non-streaming response to check tools
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": self.tools,
                "stream": False  # Need full response for tool_calls
            }
            response = await client.post(f"{self.url}/api/chat", json=payload)
            data = response.json()
            
            message = data["message"]
            
            # Check if LLM wants to call tools
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    
                    # Log tool call
                    await SupabaseDB.log_event(session_id, EventType.FUNCTION_CALL, {
                        "function": func_name,
                        "args": func_args,
                        # "result": result,
                        "query":messages[-1]["content"] if messages else "", 
                    })
                    
                    # Execute tool
                    result = await self._execute_tool(func_name, func_args)
                    
                    # Log tool result
                    await SupabaseDB.log_event(session_id, EventType.TOOL_RESULT, {
                        "function": func_name,
                        # "args": func_args,
                        "result": result,
                        "query":messages[-1]["content"] if messages else "", 
                    })
                    
                    # Add tool result back to conversation
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result),
                        "tool_call_id": tool_call.id
                    })
                
                # STEP 3: Get final human response with tool results
                final_payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.7}
                }
                
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream("POST", f"{self.url}/api/chat", json=final_payload) as final_response:
                        yield json.dumps({
    "type": "function_call",
    "function": func_name,
    "args": func_args
})
                        async for line in final_response.aiter_lines():
                            if not line: continue
                            chunk_data = json.loads(line)
                            if "message" in chunk_data and chunk_data["message"].get("content"):
                                    content = chunk_data["message"]["content"]
                                    full_response += content
                                    yield content
                                
                                    if chunk_data.get("done", False):
                                        await SupabaseDB.log_event(session_id, EventType.AI_RESPONSE, {
                                        "response": full_response,
                                        "responded_to_query": messages[-2]["content"] if messages else ""
                                    })                                        
                                    break
                                
                                 
            
            else: #if no tools required
                    payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.7}  
                }
            
            
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        async with client.stream("POST", f"{self.url}/api/chat", json=payload) as response:
                            if response.status_code != 200:
                                yield f"❌ Ollama error: {response.status_code}"
                                return
                            
                            async for line in response.aiter_lines():
                                if not line: continue
                                
                                chunk_data = json.loads(line)
                                if "message" in chunk_data and chunk_data["message"].get("content"):
                                    content = chunk_data["message"]["content"]
                                    full_response += content
                                    yield content
                                
                                    if chunk_data.get("done", False):
                                        await SupabaseDB.log_event(session_id, EventType.AI_RESPONSE, {
                                            "response": full_response,
                                            "responded_to_query": messages[-1]["content"] if messages else ""
                                        })
                                        break
            
            await SupabaseDB.update_session(session_id)
        except httpx.ConnectError:
            error_msg = f"✗ Cannot connect to Ollama at {self.url}. Is Ollama running? (ollama serve)"
            logger.error(error_msg)
            yield f"\n\n❌ ERROR: {error_msg}"
        
        except Exception as e:
            error_msg = f"❌ LLM error: {str(e)}"
            logger.error(error_msg)
            yield error_msg
                                    
    
    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute real tools"""
        if tool_name == "get_weather":
            location = args.get("location", "Unknown")
            # Simulate real API
            return {
                "location": location,
                "temperature": "72°F",
                "conditions": "Sunny",
                "humidity": "45%",
                "source": "weather_api"
            }
        
        elif tool_name == "search_knowledge_base":
            query = args.get("query", "")
            return {
                "query": query,
                "results": [f"Found info on '{query}'", "Related documents"],
                "source": "knowledge_base"
            }
        
        return {"error": f"Unknown tool: {tool_name}"}

# class LLMService:
#     """Ollama (qwen2.5:3b) streaming service - 100% FREE LOCAL API"""
    
#     def __init__(self):
#         self.url = Config.OLLAMA_URL
#         self.model = Config.OLLAMA_MODEL
#         self.system_prompt = self._get_system_prompt()
#         self.tools = self._define_tools()
    
#     def _get_system_prompt(self) -> str:
#         """System prompt that guides Ollama behavior"""
#         return """You are a helpful AI assistant with access to tools. 
# When you need external data, you can use the available tools/functions.
# Always respond naturally and helpfully. Be concise but informative.
# When function results are provided, incorporate them into your response.
# If the user asks about weather, search results, or data retrieval, you can use the available tools."""
    
#     def _define_tools(self) -> List[Dict[str, Any]]:
#         """Define available tools/functions"""
#         return [
#             {
#                 "name": "get_weather",
#                 "description": "Get current weather for a location"
#             },
#             {
#                 "name": "search_knowledge_base",
#                 "description": "Search internal knowledge base for information"
#             }
#         ]
    
#     async def stream_response(self, 
#                             messages: List[Dict[str, str]], 
#                             session_id: str) -> AsyncGenerator[str, None]:
#         """Stream response from Ollama qwen2.5:3b"""
#         full_response = ""
        
#         try:
#             # Construct messages for Ollama
#             ollama_messages = [
#                 {"role": "system", "content": self.system_prompt},
#                 *messages
#             ]
            
#             # Prepare Ollama API request
#             payload = {
#                 "model": self.model,
#                 "messages": ollama_messages,
#                 "stream": True,
#                 "options": {
#                     "temperature": 0.7,
#                     "top_p": 0.9,
#                     "num_predict": 2048,
#                     "top_k": 40
#                 }
#             }
            
#             logger.info(f"🤖 Calling Ollama: {self.url}/api/chat")
            
#             # Stream response from Ollama
#             async with httpx.AsyncClient(timeout=60.0) as client:
#                 async with client.stream(
#                     "POST", 
#                     f"{self.url}/api/chat", 
#                     json=payload
#                 ) as response:
                    
#                     if response.status_code != 200:
#                         error_msg = f"Ollama API error: {response.status_code}"
#                         logger.error(f"✗ {error_msg}")
#                         yield error_msg
#                         return
                    
#                     # Stream response line by line
#                     async for line in response.aiter_lines():
#                         if not line:
#                             continue
                        
#                         try:
#                             chunk_data = json.loads(line)
                            
#                             # Extract content from response
#                             if "message" in chunk_data:
#                                 content = chunk_data["message"].get("content", "")
#                                 if content:
#                                     full_response += content
#                                     yield content
                            
#                             # Check if response is done
#                             if chunk_data.get("done", False):
#                                 await SupabaseDB.log_event(session_id, EventType.AI_RESPONSE, {
#                 "response": full_response,
#                 "responded_to_query": messages[-1]["content"] if messages else "",
#                 # "result": result
#             })
#                                 break
                                
#                         except json.JSONDecodeError:
#                             continue
            
#             # Detect and execute tools based on response and user message
#             await self._detect_and_execute_tools(
#                 # full_response, 
#                 messages[-1]["content"] if messages else "", 
#                 session_id
#             )
            
#             logger.info(f"✓ Response complete from Ollama")
        
#         except httpx.ConnectError:
#             error_msg = f"✗ Cannot connect to Ollama at {self.url}. Is Ollama running? (ollama serve)"
#             logger.error(error_msg)
#             yield f"\n\n❌ ERROR: {error_msg}"
#         except Exception as e:
#             error_msg = f"Ollama streaming error: {str(e)}"
#             logger.error(f"✗ {error_msg}")
#             yield f"\n\n❌ ERROR: {error_msg}"
    
#     async def _detect_and_execute_tools(
#         self, 
#         # response_text: str, 
#         user_message: str, 
#         session_id: str
#     ) -> Optional[Dict[str, Any]]:
#         """Simulate function calling by detecting tool usage patterns"""
#         user_lower = user_message.lower()
        
#         # Detect weather intent
#         if any(word in user_lower for word in ["weather", "temperature", "climate", "forecast"]):
#             result = await self._execute_tool("get_weather", {"location": "detected_from_query"})
#             await SupabaseDB.log_event(session_id, EventType.FUNCTION_CALL, {
#                 "function": "get_weather",
#                 "detected_from_query": user_message,
#                 "result": result
#             })
#             return {"tool_name": "get_weather", "result": result}
        
#         # Detect search intent
#         elif any(word in user_lower for word in ["search", "find", "look up", "research", "tell me about"]):
#             result = await self._execute_tool("search_knowledge_base", {"query": user_message})
#             await SupabaseDB.log_event(session_id, EventType.FUNCTION_CALL, {
#                 "function": "search_knowledge_base",
#                 "query": user_message,
#                 "result": result
#             })
#             return {"tool_name": "search_knowledge_base", "result": result}
        
#         return None
    
#     async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
#         """Execute simulated tools and return results"""
#         if tool_name == "get_weather":
#             location = args.get("location", "Unknown Location")
#             # Deterministic simulation based on location
#             temp_base = hash(location) % 20
#             humidity_base = hash(location) % 30
            
#             return {
#                 "location": location,
#                 "temperature": f"{72 + temp_base}°F",
#                 "conditions": "Clear skies",
#                 "humidity": f"{50 + humidity_base}%",
#                 "wind": f"{5 + (hash(location) % 10)} mph",
#                 "source": "simulated_weather_service"
#             }
        
#         elif tool_name == "search_knowledge_base":
#             query = args.get("query", "")
#             return {
#                 "query": query,
#                 "results": [
#                     f"1. Information about '{query[:30]}...'",
#                     f"2. Related resources on {query.split()[0] if query.split() else 'topic'}",
#                     "3. Additional context and examples available"
#                 ],
#                 "result_count": 3,
#                 "source": "simulated_knowledge_base"
#             }
        
#         return {"error": f"Unknown tool: {tool_name}"}
