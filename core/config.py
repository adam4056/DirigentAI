import json
import os
from typing import Dict, Any, Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


class DirigentConfig:
    """Configuration manager for DirigentAI."""

    DEFAULT_PROVIDER_ENVS = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "cohere": "COHERE_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "xai": "XAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "config/dirigent.yaml"
        self.legacy_config_file = "config/dirigent.json"
        self._config = self._load_config()
        self._apply_llm_policy()

    def _load_config(self) -> Dict[str, Any]:
        default_config = {
            "llm_policy": {
                "approved_models": ["gemini-1.5-flash"],
                "force_primary_for_all_roles": False,
            },
            "model_mapping": {
                "dirigent": "gemini-1.5-flash",
                "coding": "gpt-4o-mini",
                "research": "claude-3-haiku",
                "analysis": "gemini-1.5-flash",
                "system": "gpt-4o-mini",
                "creative": "claude-3-sonnet",
            },
            "orchestrator": {
                "model": "gemini-1.5-flash",
                "api_key_env": "GEMINI_API_KEY",
                "temperature": 0.1,
                "max_tokens": 2048,
            },
            "workers": {
                "max_workers": 15,
                "presets": {
                    "coder": {
                        "capabilities": ["terminal", "file_ops"],
                        "task_type": "coding",
                        "model": "gpt-4o-mini",
                        "description": "Specialized in programming and code analysis",
                    },
                    "researcher": {
                        "capabilities": ["web_ops", "browser_ops", "file_ops"],
                        "task_type": "research",
                        "model": "claude-3-haiku",
                        "description": "Specialized in web research, browsing, and data gathering",
                    },
                    "browser_researcher": {
                        "capabilities": ["browser_ops", "web_ops", "file_ops"],
                        "task_type": "research",
                        "model": "claude-3-haiku",
                        "description": "Specialized in dynamic websites, login flows, and browser-driven research",
                    },
                    "analyzer": {
                        "capabilities": ["file_ops"],
                        "task_type": "analysis",
                        "model": "gemini-1.5-flash",
                        "description": "Specialized in data analysis and processing",
                    },
                    "admin": {
                        "capabilities": ["terminal", "file_ops"],
                        "task_type": "system",
                        "model": "gpt-4o-mini",
                        "description": "Specialized in system administration",
                    },
                },
                "default_model": "gpt-3.5-turbo",
            },
            "providers": {
                "openai": {"api_key_env": "OPENAI_API_KEY"},
                "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
                "google": {"api_key_env": "GEMINI_API_KEY"},
                "mistral": {"api_key_env": "MISTRAL_API_KEY"},
                "cohere": {"api_key_env": "COHERE_API_KEY"},
                "groq": {"api_key_env": "GROQ_API_KEY"},
                "openrouter": {"api_key_env": "OPENROUTER_API_KEY"},
                "xai": {"api_key_env": "XAI_API_KEY"},
                "deepseek": {"api_key_env": "DEEPSEEK_API_KEY"},
            },
            "security": {
                "command_blacklist": [
                    "rm -rf /", "rm -rf /*", "rm -rf .", "rm -rf *",
                    "format c:", "del /f /s /q", "shutdown", "reboot",
                ],
                "require_confirmation": False,
                "sandbox_mode": False,
            },
            "ui": {
                "hide_worker_creation": True,
                "show_technical_details": False,
                "language": "en",
            },
        }

        loaded_config: Dict[str, Any] = {}
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as handle:
                    loaded_config = yaml.safe_load(handle) or {}
            elif os.path.exists(self.legacy_config_file):
                with open(self.legacy_config_file, "r", encoding="utf-8") as handle:
                    loaded_config = json.load(handle)
        except Exception as e:
            print(f"Error loading config file: {e}. Using defaults.")
            loaded_config = {}

        if loaded_config:
            self._deep_merge(default_config, loaded_config)
        return default_config

    def _deep_merge(self, base: Dict, update: Dict) -> None:
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _infer_provider_from_model(self, model: str) -> Optional[str]:
        model_lower = (model or "").lower()
        if model_lower.startswith("openrouter/"):
            return "openrouter"
        if model_lower.startswith("deepseek"):
            return "deepseek"
        if model_lower.startswith("gpt-") or model_lower.startswith("o1") or model_lower.startswith("o3") or model_lower.startswith("o4"):
            return "openai"
        if model_lower.startswith("claude-"):
            return "anthropic"
        if model_lower.startswith("gemini-") or model_lower.startswith("google/"):
            return "gemini"
        if model_lower.startswith("groq/") or model_lower.startswith("llama-") or model_lower.startswith("qwen/") or model_lower.startswith("meta-llama/") or model_lower.startswith("openai/gpt-oss"):
            return "groq"
        if model_lower.startswith("mistral") or model_lower.startswith("codestral") or model_lower.startswith("magistral"):
            return "mistral"
        if model_lower.startswith("command-"):
            return "cohere"
        if model_lower.startswith("grok-") or model_lower.startswith("xai/"):
            return "xai"
        return None

    def _get_provider_env_var(self, provider: Optional[str]) -> Optional[str]:
        if not provider:
            return None
        providers = self._config.get("providers", {})
        provider_config = providers.get(provider, {})
        env_var = provider_config.get("api_key_env")
        if env_var:
            return env_var
        return self.DEFAULT_PROVIDER_ENVS.get(provider)

    def _model_has_available_key(self, model: str) -> bool:
        provider = self._infer_provider_from_model(model)
        env_var = self._get_provider_env_var(provider)
        if not env_var:
            return False
        return bool(os.getenv(env_var))

    def _apply_llm_policy(self) -> None:
        policy = self._config.setdefault("llm_policy", {})
        orchestrator = self._config.setdefault("orchestrator", {})
        primary_model = orchestrator.get("model") or self._config.get("model_mapping", {}).get("dirigent")
        if not primary_model:
            primary_model = "gemini-1.5-flash"
            orchestrator["model"] = primary_model

        approved_models = [m for m in policy.get("approved_models", []) if m]
        if primary_model not in approved_models:
            approved_models.insert(0, primary_model)

        approved_models = list(dict.fromkeys(approved_models))
        available_models = [model for model in approved_models if self._model_has_available_key(model)]
        if not available_models and self._model_has_available_key(primary_model):
            available_models = [primary_model]
        elif not available_models:
            available_models = approved_models[:1]

        primary_model = available_models[0]
        policy["approved_models"] = approved_models
        policy["available_models"] = available_models
        policy["force_primary_for_all_roles"] = len(available_models) == 1

        orchestrator["model"] = primary_model
        primary_provider = self._infer_provider_from_model(primary_model)
        primary_env_var = self._get_provider_env_var(primary_provider)
        if primary_provider:
            orchestrator["provider"] = primary_provider
        if primary_env_var:
            orchestrator["api_key_env"] = primary_env_var

        mapping = self._config.setdefault("model_mapping", {})
        normalized_mapping = {}
        for task_type, model in mapping.items():
            normalized_mapping[task_type] = self.resolve_model(model)
        normalized_mapping["dirigent"] = primary_model
        self._config["model_mapping"] = normalized_mapping

        workers = self._config.setdefault("workers", {})
        workers["default_model"] = self.resolve_model(workers.get("default_model") or primary_model)
        presets = workers.setdefault("presets", {})
        for preset_config in presets.values():
            task_type = preset_config.get("task_type")
            preferred_model = self._config["model_mapping"].get(task_type, preset_config.get("model"))
            preset_config["model"] = self.resolve_model(preferred_model)

    def get_approved_models(self) -> list[str]:
        return list(self._config.get("llm_policy", {}).get("approved_models", []))

    def get_available_models(self) -> list[str]:
        return list(self._config.get("llm_policy", {}).get("available_models", []))

    def resolve_model(self, preferred_model: Optional[str] = None) -> str:
        policy = self._config.get("llm_policy", {})
        available_models = list(policy.get("available_models", []))
        primary_model = self._config.get("orchestrator", {}).get("model", "gemini-1.5-flash")
        if not available_models:
            return primary_model
        if policy.get("force_primary_for_all_roles", False):
            return available_models[0]
        if preferred_model and preferred_model in available_models:
            return preferred_model
        return available_models[0]

    def get_orchestrator_config(self) -> Dict[str, Any]:
        config = self._config["orchestrator"].copy()
        config["model"] = self.resolve_model(config.get("model"))
        env_var = config.get("api_key_env")
        if env_var:
            config["api_key"] = os.getenv(env_var)
        return config

    def get_workers_config(self) -> Dict[str, Any]:
        worker_config = json.loads(json.dumps(self._config["workers"]))
        worker_config["default_model"] = self.resolve_model(worker_config.get("default_model"))
        for preset_config in worker_config.get("presets", {}).values():
            task_type = preset_config.get("task_type")
            preferred_model = self._config.get("model_mapping", {}).get(task_type, preset_config.get("model"))
            preset_config["model"] = self.resolve_model(preferred_model)
        return worker_config

    def get_worker_config(self, preset: Optional[str] = None) -> Dict[str, Any]:
        worker_config = self.get_workers_config()
        if preset and preset in worker_config.get("presets", {}):
            preset_config = worker_config["presets"][preset].copy()
            if "model" not in preset_config:
                preset_config["model"] = worker_config.get("default_model", self.resolve_model())
            return preset_config
        return {
            "model": worker_config.get("default_model", self.resolve_model()),
            "capabilities": ["terminal", "file_ops"],
        }

    def get_model_mapping(self) -> Dict[str, str]:
        return self._config.get("model_mapping", {}).copy()

    def get_model_for_task(self, task_type: str) -> Optional[str]:
        mapping = self.get_model_mapping()
        return self.resolve_model(mapping.get(task_type))

    def get_providers_config(self) -> Dict[str, Any]:
        return self._config.get("providers", {}).copy()

    def get_security_config(self) -> Dict[str, Any]:
        return self._config["security"].copy()

    def get_ui_config(self) -> Dict[str, Any]:
        return self._config["ui"].copy()

    def save_config(self) -> None:
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self._config, handle, sort_keys=False, allow_unicode=True)

    def update_config(self, updates: Dict[str, Any]) -> None:
        self._deep_merge(self._config, updates)
        self._apply_llm_policy()
        self.save_config()
