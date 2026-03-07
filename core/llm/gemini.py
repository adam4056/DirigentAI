import os
import logging
from typing import List, Dict, Optional, Any
from google import genai
from google.genai import types
from .base import LLMClient

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    """Gemini API client implementation."""
    
    def __init__(self, model_name: str = "gemini-3-flash-preview", api_key: Optional[str] = None):
        """
        Initialize Gemini client.
        
        Args:
            model_name: Gemini model name
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self.model_name = model_name
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        self.client = genai.Client(api_key=self.api_key)
    
    def generate_content(
        self,
        system_instruction: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                continue  # System instruction handled separately
            elif msg["role"] == "user":
                # Check for tool results in user messages
                if "tool_results" in msg:
                    for tool_result in msg.get("tool_results", []):
                        function_response = types.Part.from_function_response(
                            name=tool_result["name"],
                            response={"result": tool_result["result"]}
                        )
                        contents.append(
                            types.Content(role="user", parts=[function_response])
                        )
                else:
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part(text=msg.get("content", ""))]
                    ))
            elif msg["role"] == "assistant":
                # Check for tool calls in assistant messages
                if "tool_calls" in msg:
                    # Create model content with function calls
                    parts = []
                    for tool_call in msg.get("tool_calls", []):
                        parts.append(types.Part.from_function_call(
                            name=tool_call["name"],
                            args=tool_call["args"]
                        ))
                    # Add text part if there's content
                    if msg.get("content"):
                        parts.insert(0, types.Part(text=msg["content"]))
                    contents.append(types.Content(
                        role="model",
                        parts=parts
                    ))
                else:
                    contents.append(types.Content(
                        role="model",
                        parts=[types.Part(text=msg.get("content", ""))]
                    ))
        
        # Convert tools to Gemini format
        gemini_tools = None
        if tools:
            # Check if tools already contains 'function_declarations' (nested format)
            if len(tools) == 1 and "function_declarations" in tools[0]:
                # Already in Gemini Tool format
                gemini_tools = [types.Tool(function_declarations=tools[0]["function_declarations"])]
            else:
                # Assume tools is a list of function declarations
                gemini_tools = [types.Tool(function_declarations=tools)]
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            # Extract text and tool calls
            text = response.text or ""
            tool_calls = []
            
            if response.candidates and response.candidates[0].content:
                model_content = response.candidates[0].content
                for part in model_content.parts:
                    if part.function_call:
                        tool_calls.append({
                            "name": part.function_call.name,
                            "args": part.function_call.args,
                        })
            
            return {
                "text": text,
                "tool_calls": tool_calls,
                "raw_response": response,
            }
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
    
    def supports_function_calling(self) -> bool:
        return True
    
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "gemini",
            "model": self.model_name,
            "supports_function_calling": True,
        }