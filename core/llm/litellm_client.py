import json
import os
import logging
from typing import List, Dict, Optional, Any
import litellm
from litellm import ModelResponse
from .base import LLMClient

logger = logging.getLogger(__name__)


class LiteLLMClient(LLMClient):
    """LiteLLM client for unified multi-provider support."""
    
    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        """
        Initialize LiteLLM client.
        
        Args:
            model: Model string (e.g., "gpt-4", "claude-3-sonnet", "gemini-1.5-pro")
            api_key: Optional API key (uses environment variables if not provided)
            **kwargs: Additional LiteLLM configuration
        """
        self.model = model
        self.api_key = api_key
        self.config = kwargs
        
        # Set API key in environment if provided
        if api_key:
            self._set_api_key_for_model(model, api_key)
    
    def _set_api_key_for_model(self, model: str, api_key: str):
        """Set appropriate environment variable for the model provider."""
        model_lower = model.lower()
        
        if "gpt" in model_lower or "openai" in model_lower:
            os.environ["OPENAI_API_KEY"] = api_key
        elif "claude" in model_lower or "anthropic" in model_lower:
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif "gemini" in model_lower or "google" in model_lower:
            os.environ["GEMINI_API_KEY"] = api_key
        elif "mistral" in model_lower:
            os.environ["MISTRAL_API_KEY"] = api_key
        elif "cohere" in model_lower:
            os.environ["COHERE_API_KEY"] = api_key
        # OpenRouter uses OPENROUTER_API_KEY
        # Groq uses GROQ_API_KEY
        # etc.
    
    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert our internal message format to LiteLLM format."""
        litellm_messages = []
        
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "system":
                # LiteLLM handles system messages differently
                # We'll prepend system instruction separately
                continue
            if role == "tool":
                litellm_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", "call_unknown"),
                    "name": msg.get("name", "tool"),
                    "content": str(content),
                })
                continue
            if role == "user":
                # Backward compatibility for older stored tool wrapper messages.
                if "tool_results" in msg:
                    for tool_result in msg.get("tool_results", []):
                        litellm_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_result.get("tool_call_id", "call_unknown"),
                            "name": tool_result.get("name", "tool"),
                            "content": str(tool_result["result"]),
                        })
                else:
                    litellm_messages.append({"role": "user", "content": content})
                continue
            if role == "assistant":
                if "tool_calls" in msg:
                    tool_calls = []
                    for tool_call in msg.get("tool_calls", []):
                        tool_calls.append({
                            "id": tool_call.get("id") or f"call_{tool_call['name']}",
                            "type": "function",
                            "function": {
                                "name": tool_call["name"],
                                "arguments": json.dumps(tool_call.get("args", {})),
                            },
                        })

                    litellm_messages.append({
                        "role": "assistant",
                        "content": content if content else None,
                        "tool_calls": tool_calls,
                    })
                else:
                    litellm_messages.append({"role": "assistant", "content": content})
        
        return litellm_messages
    
    def _convert_tools(self, tools: Optional[List[Dict]]) -> Optional[List[Dict]]:
        """Convert our tool definitions to LiteLLM format."""
        if not tools:
            return None
        
        litellm_tools = []
        for tool in tools:
            litellm_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                }
            })
        
        return litellm_tools
    
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
        Generate a response using LiteLLM.
        
        Args:
            system_instruction: System prompt/instruction
            messages: List of message dicts
            tools: List of tool definitions
            tool_choice: How to handle tool calls
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Dict with 'text' and 'tool_calls' keys
        """
        try:
            # Convert messages and tools
            litellm_messages = self._convert_messages(messages)
            
            # Add system instruction as first message
            if system_instruction:
                litellm_messages.insert(0, {"role": "system", "content": system_instruction})
            
            # Convert tools
            litellm_tools = self._convert_tools(tools)
            
            # Prepare parameters
            params = {
                "model": self.model,
                "messages": litellm_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **self.config
            }
            
            if litellm_tools:
                params["tools"] = litellm_tools
                if tool_choice:
                    params["tool_choice"] = tool_choice
            
            # Call LiteLLM
            response: ModelResponse = litellm.completion(**params)
            
            # Extract text and tool calls from response
            message = response.choices[0].message
            
            text = message.content or ""
            tool_calls = []
            
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function":
                        # Parse arguments from string
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except (json.JSONDecodeError, AttributeError):
                            args = {}
                        
                        tool_calls.append({
                            "id": getattr(tool_call, "id", None),
                            "name": tool_call.function.name,
                            "args": args
                        })
            
            return {
                "text": text,
                "tool_calls": tool_calls,
                "raw_response": response,
                "model": self.model,
                "usage": getattr(response, 'usage', {}),
                "cost": litellm.completion_cost(completion_response=response)
            }
            
        except Exception as e:
            logger.error(f"LiteLLM API error for model {self.model}: {e}")
            # Try to provide helpful error messages
            if "authentication" in str(e).lower() or "api key" in str(e).lower():
                error_msg = f"Authentication error for model {self.model}. Check API key."
            elif "quota" in str(e).lower() or "limit" in str(e).lower():
                error_msg = f"Quota exceeded for model {self.model}."
            else:
                error_msg = f"Error with model {self.model}: {e}"
            
            raise Exception(error_msg) from e
    
    def supports_function_calling(self) -> bool:
        """Check if the model supports function calling."""
        # Most modern models support function calling
        # We could make this more sophisticated based on model name
        return True
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the model being used."""
        # Extract provider from model string
        model_lower = self.model.lower()
        
        provider = "unknown"
        if "gpt" in model_lower:
            provider = "openai"
        elif "claude" in model_lower:
            provider = "anthropic"
        elif "gemini" in model_lower:
            provider = "google"
        elif "mistral" in model_lower:
            provider = "mistral"
        elif "command" in model_lower:
            provider = "cohere"
        elif "llama" in model_lower:
            provider = "meta"
        elif "grok" in model_lower:
            provider = "xai"
        
        return {
            "provider": provider,
            "model": self.model,
            "supports_function_calling": self.supports_function_calling(),
        }
    
    @staticmethod
    def get_available_models() -> List[str]:
        """Get list of available models through LiteLLM."""
        # This is a simplified list - in practice you'd query LiteLLM's model list
        common_models = [
            # OpenAI
            "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
            # Anthropic
            "claude-3-5-sonnet", "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
            # Google
            "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
            # Mistral
            "mistral-large", "mistral-medium", "mistral-small",
            # Cohere
            "command-r", "command-r-plus",
            # Meta
            "llama-3-70b", "llama-3-8b",
            # XAI
            "grok-2", "grok-1",
            # OpenRouter (many models available)
            "openrouter/quasar-alpha",
        ]
        return common_models