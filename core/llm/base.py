from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
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
        Generate a response from the LLM.
        
        Args:
            system_instruction: System prompt/instruction
            messages: List of message dicts with 'role' and 'content' keys, 
                     may also include 'tool_calls' and 'tool_results' keys
            tools: List of tool definitions for function calling
            tool_choice: How to handle tool calls ('auto', 'none', or specific tool)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Dict with 'text' and 'tool_calls' keys
        """
        pass
    
    @abstractmethod
    def supports_function_calling(self) -> bool:
        """Return True if this provider supports function calling."""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the model being used."""
        pass