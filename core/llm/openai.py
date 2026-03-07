import os
import logging
from typing import List, Dict, Optional, Any

try:
    import openai
    from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from .base import LLMClient

logger = logging.getLogger(__name__)


class OpenAIError(Exception):
    pass


class OpenAIClient(LLMClient):
    """OpenAI API client implementation."""
    
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        """
        Initialize OpenAI client.
        
        Args:
            model_name: OpenAI model name
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        if not HAS_OPENAI:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = openai.OpenAI(api_key=self.api_key)
    
    def generate_content(
        self,
        system_instruction: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Generate a response using OpenAI API.
        
        OpenAI expects messages in format:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "...", "tool_calls": [...]},
            {"role": "tool", "content": "...", "tool_call_id": "..."},
        ]
        """
        # Convert messages to OpenAI format
        openai_messages = []
        
        # Add system instruction as first message
        if system_instruction:
            openai_messages.append({"role": "system", "content": system_instruction})
        
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            
            if role == "system":
                # Already handled
                continue
            elif role == "user":
                # Check for tool results
                if "tool_results" in msg:
                    for tool_result in msg.get("tool_results", []):
                        openai_messages.append({
                            "role": "tool",
                            "content": tool_result["result"],
                            "tool_call_id": f"call_{tool_result['name']}",  # Simplified ID
                        })
                else:
                    openai_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # Check for tool calls
                if "tool_calls" in msg:
                    tool_calls = []
                    for tool_call in msg.get("tool_calls", []):
                        tool_calls.append({
                            "id": f"call_{tool_call['name']}",
                            "type": "function",
                            "function": {
                                "name": tool_call["name"],
                                "arguments": str(tool_call["args"]),  # JSON string
                            }
                        })
                    openai_messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    })
                else:
                    openai_messages.append({"role": "assistant", "content": content})
        
        # Convert tools to OpenAI format
        openai_tools = None
        if tools:
            openai_tools = []
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    }
                })
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                tools=openai_tools,
                tool_choice=tool_choice or ("auto" if tools else "none"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            message = response.choices[0].message
            text = message.content or ""
            tool_calls = []
            
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function":
                        # Parse arguments from JSON string
                        import json
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            args = {}
                        
                        tool_calls.append({
                            "name": tool_call.function.name,
                            "args": args,
                        })
            
            return {
                "text": text,
                "tool_calls": tool_calls,
                "raw_response": response,
            }
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    def supports_function_calling(self) -> bool:
        return True
    
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "openai",
            "model": self.model_name,
            "supports_function_calling": True,
        }