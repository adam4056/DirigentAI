import os
import logging
from typing import Dict, Any, Optional
from .base import LLMClient
from .litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM clients using LiteLLM for multi-provider support."""

    _PROVIDER_PREFIXES = {
        "deepseek": "deepseek/",
        "openrouter": "openrouter/",
        "xai": "xai/",
        "groq": "groq/",
    }

    @staticmethod
    def infer_provider_from_model(model: Optional[str]) -> Optional[str]:
        model_lower = (model or "").lower()
        if model_lower.startswith("openrouter/"):
            return "openrouter"
        if model_lower.startswith("deepseek/") or model_lower.startswith("deepseek-"):
            return "deepseek"
        if model_lower.startswith("xai/") or model_lower.startswith("grok"):
            return "xai"
        if model_lower.startswith("groq/"):
            return "groq"
        if model_lower.startswith("gpt-") or model_lower.startswith("o1") or model_lower.startswith("o3") or model_lower.startswith("o4"):
            return "openai"
        if model_lower.startswith("claude"):
            return "anthropic"
        if model_lower.startswith("gemini") or model_lower.startswith("google/"):
            return "gemini"
        if model_lower.startswith("mistral") or model_lower.startswith("codestral") or model_lower.startswith("magistral"):
            return "mistral"
        if model_lower.startswith("command"):
            return "cohere"
        if model_lower.startswith("llama-") or model_lower.startswith("qwen/") or model_lower.startswith("meta-llama/") or model_lower.startswith("openai/gpt-oss"):
            return "groq"
        return None

    @staticmethod
    def normalize_model_string(model: str, provider: Optional[str] = None) -> str:
        inferred_provider = LLMFactory.infer_provider_from_model(model)
        provider = (inferred_provider or provider or "").lower()
        prefix = LLMFactory._PROVIDER_PREFIXES.get(provider)
        if not prefix:
            return model
        if model.lower().startswith(prefix):
            return model
        return f"{prefix}{model}"
    
    # Default model mappings for backward compatibility
    _DEFAULT_MODELS = {
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-5-mini",
        "anthropic": "claude-sonnet-4-20250514",
        "mistral": "mistral-small-latest",
        "cohere": "command-a-03-2025",
        "groq": "llama-3.1-8b-instant",
        "openrouter": "openai/gpt-5-mini",
        "xai": "grok-4-fast",
        "deepseek": "deepseek-chat",
    }
    
    @staticmethod
    def create_client(
        provider: str = "gemini",
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> LLMClient:
        """
        Create an LLM client for the specified provider.
        
        Args:
            provider: LLM provider ('gemini', 'openai', 'anthropic', etc.)
            model_name: Model name to use (provider-specific)
            api_key: API key (defaults to provider-specific env var)
            **kwargs: Additional provider-specific arguments
            
        Returns:
            LLMClient instance
        """
        provider = provider.lower()
        
        # Determine the model string
        if model_name:
            # User specified a model name - normalize it for LiteLLM when needed
            model = LLMFactory.normalize_model_string(model_name, provider)
        else:
            # Use default model for the provider
            model = LLMFactory._DEFAULT_MODELS.get(provider)
            if not model:
                raise ValueError(f"No default model defined for provider: {provider}")
        
        # For backward compatibility, ensure provider-specific API keys are set
        if api_key:
            LLMFactory._set_provider_api_key(provider, api_key)
        
        # Create LiteLLM client
        normalized_model = LLMFactory.normalize_model_string(model, provider)
        return LiteLLMClient(model=normalized_model, api_key=api_key, **kwargs)
    
    @staticmethod
    def create_client_from_model(
        model: str,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs,
    ) -> LLMClient:
        """
        Create an LLM client directly from model string.
        
        Args:
            model: Model string (e.g., "gpt-4", "claude-3-sonnet", "gemini-1.5-pro")
            api_key: Optional API key
            **kwargs: Additional configuration
            
        Returns:
            LLMClient instance
        """
        normalized_model = LLMFactory.normalize_model_string(model, provider)
        inferred_provider = LLMFactory.infer_provider_from_model(normalized_model) or provider
        if api_key and inferred_provider:
            LLMFactory._set_provider_api_key(inferred_provider, api_key)
        return LiteLLMClient(model=normalized_model, api_key=api_key, **kwargs)
    
    @staticmethod
    def create_client_from_config(config: Dict[str, Any]) -> LLMClient:
        """
        Create LLM client from configuration dictionary.
        
        Supports both old format (provider + model) and new format (model only).
        
        Old format (backward compatible):
        {
            "provider": "gemini",
            "model": "gemini-3-flash-preview",
            "api_key": "sk-...",
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        
        New format (recommended):
        {
            "model": "gpt-4o-mini",
            "api_key": "sk-...",
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        """
        # Check if new format (model directly specified)
        if "model" in config and config["model"]:
            model = config["model"]
            api_key = config.get("api_key")
            provider = config.get("provider")
            
            # Extract any LiteLLM-specific config
            llm_config = {k: v for k, v in config.items() 
                         if k not in ["model", "api_key", "provider"]}
            
            return LLMFactory.create_client_from_model(
                model=model,
                api_key=api_key,
                provider=provider,
                **llm_config
            )
        
        # Fallback to old format
        provider = config.get("provider", "gemini")
        model_name = config.get("model")
        api_key = config.get("api_key")
        
        # Extract any additional config
        llm_config = {k: v for k, v in config.items() 
                     if k not in ["provider", "model", "api_key"]}
        
        return LLMFactory.create_client(
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            **llm_config
        )
    
    @staticmethod
    def _set_provider_api_key(provider: str, api_key: str) -> None:
        """Set environment variable for provider API key."""
        env_vars = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "cohere": "COHERE_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        
        env_var = env_vars.get(provider)
        if env_var:
            os.environ[env_var] = api_key
    
    @staticmethod
    def get_available_models() -> list:
        """Get list of available models through LiteLLM."""
        try:
            return LiteLLMClient.get_available_models()
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return list(LLMFactory._DEFAULT_MODELS.values())