import json
import os

import yaml
import signal
import socket
import subprocess
import sys
import time
from copy import deepcopy

from colorama import Fore, Style, init
from dotenv import dotenv_values, load_dotenv

init()

processes = []
CONFIG_PATH = "config/dirigent.yaml"
LEGACY_CONFIG_PATH = "config/dirigent.json"
ENV_PATH = ".env"
TASK_ROLES = ["dirigent", "coding", "research", "analysis", "system", "creative"]
ROLE_LABELS = {
    "dirigent": "CEO / orchestrator",
    "coding": "Coding workers",
    "research": "Research workers",
    "analysis": "Analysis workers",
    "system": "System/admin workers",
    "creative": "Creative tasks",
}
ENV_KEYS = [
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USER_IDS",
]
PROVIDER_CATALOG = {
    "gemini": {
        "key": "1",
        "label": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
        "note": "Official Gemini API lineup with stable 2.5 models plus current preview examples.",
        "models": [
            {"label": "Gemini 2.5 Flash", "model": "gemini-2.5-flash", "note": "Recommended balanced default from the current stable lineup.", "tag": "Recommended"},
            {"label": "Gemini 2.5 Flash-Lite", "model": "gemini-2.5-flash-lite", "note": "Lowest-cost high-throughput option.", "tag": "Budget"},
            {"label": "Gemini 2.5 Pro", "model": "gemini-2.5-pro", "note": "Best for harder reasoning and coding tasks.", "tag": "Power"},
            {"label": "Gemini 3 Flash Preview", "model": "gemini-3-flash-preview", "note": "Frontier-class preview model for experimentation.", "tag": "Preview"},
            {"label": "Gemini 2.5 Flash-Lite Preview", "model": "gemini-2.5-flash-lite-preview-09-2025", "note": "Preview variant when you want the newest Flash-Lite behavior.", "tag": "Preview"},
        ],
    },
    "openai": {
        "key": "2",
        "label": "OpenAI",
        "env_var": "OPENAI_API_KEY",
        "note": "Current OpenAI API lineup with fast, reasoning, and large-context options.",
        "models": [
            {"label": "GPT-5 mini", "model": "gpt-5-mini", "note": "Fast, cost-efficient default for most tasks.", "tag": "Recommended"},
            {"label": "GPT-5.2", "model": "gpt-5.2", "note": "Best coding and agentic performance in the current docs.", "tag": "Power"},
            {"label": "GPT-5.1", "model": "gpt-5.1", "note": "Strong flagship alternative with configurable reasoning.", "tag": "Flagship"},
            {"label": "GPT-4.1", "model": "gpt-4.1", "note": "Strong non-reasoning model with large context and good tool use.", "tag": "Large Context"},
            {"label": "GPT-4.1 mini", "model": "gpt-4.1-mini", "note": "Smaller and faster GPT-4.1 family model.", "tag": "Fast"},
            {"label": "GPT-4o mini", "model": "gpt-4o-mini", "note": "Cheap utility model for simple workers and glue tasks.", "tag": "Budget"},
            {"label": "o3-mini", "model": "o3-mini", "note": "Small reasoning model when you want explicit reasoning behavior.", "tag": "Reasoning"},
            {"label": "o4-mini", "model": "o4-mini", "note": "Fast reasoning model, now mostly superseded by GPT-5 mini.", "tag": "Reasoning"},
        ],
    },
    "anthropic": {
        "key": "3",
        "label": "Anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "note": "Claude lineup based on Anthropic's official model overview and aliases.",
        "models": [
            {"label": "Claude Sonnet 4", "model": "claude-sonnet-4-20250514", "note": "Current balanced Claude model for serious work.", "tag": "Recommended"},
            {"label": "Claude Opus 4.1", "model": "claude-opus-4-1-20250805", "note": "Most capable Claude option for difficult tasks.", "tag": "Power"},
            {"label": "Claude Opus 4", "model": "claude-opus-4-20250514", "note": "Previous flagship snapshot still useful for compatibility.", "tag": "Flagship"},
            {"label": "Claude 3.7 Sonnet", "model": "claude-3-7-sonnet-20250219", "note": "Reasoning-capable Sonnet generation still widely used.", "tag": "Reasoning"},
            {"label": "Claude 3.5 Sonnet", "model": "claude-3-5-sonnet-latest", "note": "Alias that tracks the latest 3.5 Sonnet snapshot.", "tag": "Alias"},
            {"label": "Claude 3.5 Haiku", "model": "claude-3-5-haiku-latest", "note": "Fast Claude option for lightweight work.", "tag": "Fast"},
        ],
    },
    "groq": {
        "key": "4",
        "label": "Groq",
        "env_var": "GROQ_API_KEY",
        "note": "GroqCloud production and preview models for very fast inference.",
        "models": [
            {"label": "Llama 3.1 8B Instant", "model": "llama-3.1-8b-instant", "note": "Fastest cheap production default in Groq docs.", "tag": "Recommended"},
            {"label": "Llama 3.3 70B Versatile", "model": "llama-3.3-70b-versatile", "note": "Better quality general-purpose production model.", "tag": "Power"},
            {"label": "Qwen3 32B", "model": "qwen/qwen3-32b", "note": "Reasoning-friendly Qwen model on Groq.", "tag": "Reasoning"},
            {"label": "Llama 4 Maverick", "model": "meta-llama/llama-4-maverick-17b-128e-instruct", "note": "Multimodal preview model with strong coding and vision support.", "tag": "Vision"},
            {"label": "Llama 4 Scout", "model": "meta-llama/llama-4-scout-17b-16e-instruct", "note": "Large-context Llama 4 preview model.", "tag": "Preview"},
            {"label": "OpenAI GPT-OSS 20B", "model": "openai/gpt-oss-20b", "note": "Cheap open-weight option with strong speed.", "tag": "Budget"},
            {"label": "OpenAI GPT-OSS 120B", "model": "openai/gpt-oss-120b", "note": "Higher-quality open-weight Groq-hosted option.", "tag": "Open Weight"},
        ],
    },
    "mistral": {
        "key": "5",
        "label": "Mistral",
        "env_var": "MISTRAL_API_KEY",
        "note": "Mistral family for general text, coding, and frontier reasoning.",
        "models": [
            {"label": "Mistral Small", "model": "mistral-small-latest", "note": "Good default for affordable general text work.", "tag": "Recommended"},
            {"label": "Mistral Medium", "model": "mistral-medium-latest", "note": "Stronger general-purpose frontier model.", "tag": "Power"},
            {"label": "Mistral Large", "model": "mistral-large-latest", "note": "Top-end large tier with broad capabilities.", "tag": "Large"},
            {"label": "Codestral", "model": "codestral-latest", "note": "Coding-focused Mistral model.", "tag": "Coding"},
            {"label": "Magistral Medium", "model": "magistral-medium-latest", "note": "Reasoning-oriented Mistral family model.", "tag": "Reasoning"},
        ],
    },
    "cohere": {
        "key": "6",
        "label": "Cohere",
        "env_var": "COHERE_API_KEY",
        "note": "Current Command family names rather than deprecated aliases.",
        "models": [
            {"label": "Command A", "model": "command-a-03-2025", "note": "Cohere's current best general model.", "tag": "Recommended"},
            {"label": "Command R+", "model": "command-r-plus-08-2024", "note": "Higher-end Command model.", "tag": "Power"},
            {"label": "Command R", "model": "command-r-08-2024", "note": "Balanced Command model with retrieval-friendly behavior.", "tag": "Balanced"},
            {"label": "Command R7B", "model": "command-r7b-12-2024", "note": "Smaller Command family option for cost-sensitive tasks.", "tag": "Budget"},
        ],
    },
    "openrouter": {
        "key": "7",
        "label": "OpenRouter",
        "env_var": "OPENROUTER_API_KEY",
        "note": "Curated examples only. OpenRouter is most useful when you pair it with custom model IDs.",
        "models": [
            {"label": "OpenAI GPT-5 mini", "model": "openai/gpt-5-mini", "note": "OpenAI via OpenRouter.", "tag": "Recommended"},
            {"label": "OpenAI GPT-5.2", "model": "openai/gpt-5.2", "note": "OpenAI flagship via OpenRouter.", "tag": "Power"},
            {"label": "Anthropic Claude Sonnet 4", "model": "anthropic/claude-sonnet-4", "note": "Claude via OpenRouter.", "tag": "Example"},
            {"label": "Google Gemini 2.5 Flash", "model": "google/gemini-2.5-flash", "note": "Gemini via OpenRouter.", "tag": "Example"},
            {"label": "Google Gemini 2.5 Pro", "model": "google/gemini-2.5-pro", "note": "Gemini reasoning via OpenRouter.", "tag": "Example"},
            {"label": "DeepSeek V3.2", "model": "deepseek/deepseek-chat", "note": "DeepSeek via OpenRouter.", "tag": "Example"},
            {"label": "Qwen3 Coder", "model": "qwen/qwen3-coder", "note": "Open model coding route through OpenRouter.", "tag": "Coding"},
        ],
    },
    "xai": {
        "key": "8",
        "label": "xAI",
        "env_var": "XAI_API_KEY",
        "note": "xAI naming changes often, so custom model ID remains important here.",
        "models": [
            {"label": "Grok 4 Fast", "model": "grok-4-fast", "note": "Fast xAI model example.", "tag": "Recommended"},
            {"label": "Grok 4", "model": "grok-4", "note": "Higher-capability Grok example.", "tag": "Power"},
            {"label": "Grok Vision Beta", "model": "grok-vision-beta", "note": "Vision-capable xAI option.", "tag": "Vision"},
        ],
    },
    "deepseek": {
        "key": "9",
        "label": "DeepSeek",
        "env_var": "DEEPSEEK_API_KEY",
        "note": "Official DeepSeek API models. Simple, cheap, and very relevant for coding/reasoning users.",
        "models": [
            {"label": "DeepSeek Chat", "model": "deepseek-chat", "note": "Non-thinking mode backed by DeepSeek-V3.2.", "tag": "Recommended"},
            {"label": "DeepSeek Reasoner", "model": "deepseek-reasoner", "note": "Thinking mode backed by DeepSeek-V3.2.", "tag": "Reasoning"},
        ],
    },
}
PROVIDER_ENV_MAP = {
    "openai": {"api_key_env": "OPENAI_API_KEY"},
    "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
    "google": {"api_key_env": "GEMINI_API_KEY"},
    "gemini": {"api_key_env": "GEMINI_API_KEY"},
    "mistral": {"api_key_env": "MISTRAL_API_KEY"},
    "cohere": {"api_key_env": "COHERE_API_KEY"},
    "groq": {"api_key_env": "GROQ_API_KEY"},
    "openrouter": {"api_key_env": "OPENROUTER_API_KEY"},
    "xai": {"api_key_env": "XAI_API_KEY"},
    "deepseek": {"api_key_env": "DEEPSEEK_API_KEY"},
}


def build_model_entry(provider_key: str, model_name: str, label: str | None = None, note: str = "") -> dict:
    provider = PROVIDER_CATALOG[provider_key]
    return {
        "provider": provider_key,
        "model": model_name,
        "env_var": provider["env_var"],
        "label": label or model_name,
        "note": note or provider.get("note", ""),
    }


def flatten_model_catalog() -> list[dict]:
    items = []
    for provider_key, provider in PROVIDER_CATALOG.items():
        for model in provider["models"]:
            items.append(build_model_entry(provider_key, model["model"], model["label"], model.get("note", "")))
    return items


MODEL_PRESETS = flatten_model_catalog()
MODEL_BY_NAME = {item["model"]: item for item in MODEL_PRESETS}
PROVIDER_BY_KEY = {provider["key"]: key for key, provider in PROVIDER_CATALOG.items()}


def print_banner():
    banner = f"""
{Fore.CYAN}   ____  _      _                 _          _    ___
  |  _ \\(_)____(_)__ _  ___ _ __ | |_      _/ |  / _ \\
  | | | | |_  / / _` |/ _ \\ '_ \\| __|____| | | | | | |
  | |_| | |/ / / (_| |  __/ | | | ||_____| | | | |_| |
  |____/|_/___/_\\__, |\\___|_| |_|\\__|    |_|_|  \\___/
                |___/
{Style.RESET_ALL}"""
    print(banner)


def print_section(title: str, body: str = ""):
    line = "=" * 68
    print(f"{Fore.CYAN}{line}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{title}{Style.RESET_ALL}")
    if body:
        print(f"{Fore.LIGHTBLACK_EX}{body}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{line}{Style.RESET_ALL}")


def prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{Fore.YELLOW}{label}{suffix}:{Style.RESET_ALL} ").strip()
    return value or default


def prompt_yes_no(label: str, default: bool = True) -> bool:
    options = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{Fore.YELLOW}{label} [{options}]:{Style.RESET_ALL} ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print(f"{Fore.RED}Please answer y or n.{Style.RESET_ALL}")


def prompt_int(label: str, default: int, minimum: int = 1) -> int:
    while True:
        raw = prompt_text(label, default=str(default))
        try:
            value = int(raw)
            if value < minimum:
                raise ValueError
            return value
        except ValueError:
            print(f"{Fore.RED}Enter an integer >= {minimum}.{Style.RESET_ALL}")


def prompt_choice(label: str, options: list[dict], default_key: str | None = None) -> dict:
    valid = {option["key"]: option for option in options}
    fallback = default_key or options[0]["key"]
    while True:
        selected = prompt_text(label, default=fallback)
        if selected in valid:
            return valid[selected]
        print(f"{Fore.RED}Pick one of: {', '.join(valid.keys())}.{Style.RESET_ALL}")


def load_existing_env() -> dict[str, str]:
    if not os.path.exists(ENV_PATH):
        return {}
    return {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}


def load_config_file() -> dict:
    if not os.path.exists(CONFIG_PATH):
        if os.path.exists(LEGACY_CONFIG_PATH):
            with open(LEGACY_CONFIG_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_env_file(env_data: dict[str, str]):
    lines = [f"{key}={value}" for key, value in env_data.items() if value]
    with open(ENV_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + ("\n" if lines else ""))


def write_config_file(config: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)


def save_all(config: dict, env_data: dict[str, str], message: str = "Configuration saved."):
    write_config_file(config)
    write_env_file(env_data)
    print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")


def infer_provider_from_model(model_name: str) -> str | None:
    lowered = (model_name or "").lower()
    if lowered.startswith("openrouter/"):
        return "openrouter"
    if lowered.startswith("deepseek"):
        return "deepseek"
    if lowered.startswith("grok") or lowered.startswith("xai/"):
        return "xai"
    if lowered.startswith("gemini") or lowered.startswith("google/"):
        return "gemini"
    if lowered.startswith("claude"):
        return "anthropic"
    if lowered.startswith("gpt") or lowered.startswith("o1") or lowered.startswith("o3") or lowered.startswith("o4"):
        return "openai"
    if lowered.startswith("mistral") or lowered.startswith("codestral") or lowered.startswith("magistral"):
        return "mistral"
    if lowered.startswith("command"):
        return "cohere"
    if lowered.startswith("llama-") or lowered.startswith("qwen/") or lowered.startswith("meta-llama/") or lowered.startswith("openai/gpt-oss"):
        return "groq"
    return None


def get_model_info(model_name: str) -> dict | None:
    known = MODEL_BY_NAME.get(model_name)
    if known:
        return deepcopy(known)
    provider_key = infer_provider_from_model(model_name)
    if not provider_key or provider_key not in PROVIDER_CATALOG:
        return None
    return build_model_entry(provider_key, model_name, label=model_name, note="Custom model ID")


def print_selected_models(selected_models: list[dict]):
    if not selected_models:
        print(f"{Fore.LIGHTBLACK_EX}No models selected yet.{Style.RESET_ALL}")
        return
    print(f"{Fore.WHITE}Approved models so far:{Style.RESET_ALL}")
    for item in selected_models:
        provider_label = PROVIDER_CATALOG[item["provider"]]["label"]
        print(f"- {provider_label}: {item['model']}")
    print()


def show_provider_catalog(selected_models: list[dict] | None = None):
    selected_models = selected_models or []
    counts = {}
    for item in selected_models:
        counts[item["provider"]] = counts.get(item["provider"], 0) + 1

    print_section("Step 1/3 - Providers", "Pick a provider first, then choose one or more models under it.")
    print_selected_models(selected_models)
    for provider_key, provider in PROVIDER_CATALOG.items():
        count = counts.get(provider_key, 0)
        badge = f" [{count} selected]" if count else ""
        total = len(provider["models"])
        print(f"{Fore.GREEN}{provider['key']}.{Style.RESET_ALL} {provider['label']} [{total} presets + custom]{badge}")
        print(f"   {Fore.LIGHTBLACK_EX}{provider['note']}{Style.RESET_ALL}")
    print()


def show_provider_models(provider_key: str, selected_models: list[dict]):
    provider = PROVIDER_CATALOG[provider_key]
    selected_names = {item["model"] for item in selected_models if item["provider"] == provider_key}
    print_section(
        f"Provider - {provider['label']}",
        "Choose curated models or enter a custom LiteLLM model ID for this provider.",
    )
    for index, model in enumerate(provider["models"], start=1):
        selected_badge = " [selected]" if model["model"] in selected_names else ""
        tag = f" [{model['tag']}]" if model.get("tag") else ""
        print(f"{Fore.GREEN}{index}.{Style.RESET_ALL} {model['label']} ({model['model']}){tag}{selected_badge}")
        print(f"   {Fore.LIGHTBLACK_EX}{model['note']}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}c.{Style.RESET_ALL} Custom model ID")
    print(f"{Fore.GREEN}d.{Style.RESET_ALL} Done with this provider")
    print()


def choose_provider(selected_models: list[dict]) -> str | None:
    allow_done = bool(selected_models)
    while True:
        show_provider_catalog(selected_models)
        label = "Select provider number or type 'done'" if allow_done else "Select provider number"
        default_value = "done" if allow_done else "1"
        choice = prompt_text(label, default=default_value).lower()
        if choice == "done" and allow_done:
            return None
        provider_key = PROVIDER_BY_KEY.get(choice)
        if provider_key:
            return provider_key
        print(f"{Fore.RED}Unknown provider choice.{Style.RESET_ALL}")


def ensure_provider_api_key(provider_key: str, env_updates: dict[str, str]) -> dict[str, str] | None:
    provider = PROVIDER_CATALOG[provider_key]
    api_key = prompt_text(f"API key for {provider['label']}", env_updates.get(provider["env_var"], ""))
    if not api_key:
        print(f"{Fore.RED}An API key is required before approving models from this provider.{Style.RESET_ALL}")
        return None
    env_updates[provider["env_var"]] = api_key
    return env_updates


def choose_provider_models(provider_key: str, selected_models: list[dict], env_updates: dict[str, str]) -> tuple[list[dict], dict[str, str]]:
    provider = PROVIDER_CATALOG[provider_key]
    selected = list(selected_models)
    env_copy = dict(env_updates)
    ensured_key = bool(env_copy.get(provider["env_var"]))

    while True:
        show_provider_models(provider_key, selected)
        default_choice = "d" if any(item["provider"] == provider_key for item in selected) else "1"
        choice = prompt_text("Pick a model, 'c' for custom, or 'd' when done", default=default_choice).lower()

        if choice == "d":
            return selected, env_copy

        if choice == "c":
            custom_model = prompt_text(f"Custom model ID for {provider['label']}")
            if not custom_model:
                print(f"{Fore.RED}Model ID cannot be blank.{Style.RESET_ALL}")
                continue
            if custom_model in {item['model'] for item in selected}:
                print(f"{Fore.YELLOW}Model already selected.{Style.RESET_ALL}")
                continue
            if not ensured_key:
                maybe_env = ensure_provider_api_key(provider_key, env_copy)
                if maybe_env is None:
                    continue
                env_copy = maybe_env
                ensured_key = True
            selected.append(build_model_entry(provider_key, custom_model, label=custom_model, note="Custom model ID"))
            print(f"{Fore.GREEN}Added {custom_model}.{Style.RESET_ALL}")
            continue

        if not choice.isdigit():
            print(f"{Fore.RED}Unknown model choice.{Style.RESET_ALL}")
            continue

        index = int(choice) - 1
        if not 0 <= index < len(provider["models"]):
            print(f"{Fore.RED}Unknown model choice.{Style.RESET_ALL}")
            continue

        curated = provider["models"][index]
        if curated["model"] in {item['model'] for item in selected}:
            print(f"{Fore.YELLOW}Model already selected.{Style.RESET_ALL}")
            continue

        if not ensured_key:
            maybe_env = ensure_provider_api_key(provider_key, env_copy)
            if maybe_env is None:
                continue
            env_copy = maybe_env
            ensured_key = True

        selected.append(build_model_entry(provider_key, curated["model"], curated["label"], curated.get("note", "")))
        print(f"{Fore.GREEN}Added {curated['model']}.{Style.RESET_ALL}")



def choose_models(existing_env: dict[str, str], preselected_models: list[str] | None = None) -> tuple[list[dict], dict[str, str]]:
    env_updates = dict(existing_env)
    selected = []
    for model_name in preselected_models or []:
        info = get_model_info(model_name)
        if info and info["model"] not in {item["model"] for item in selected}:
            selected.append(info)

    while True:
        print_section("Model Approval", "Approve only the providers and models you want DirigentAI to use.")
        print_selected_models(selected)
        print("1. Add provider and models")
        if selected:
            print("2. Remove selected model")
            print("3. Continue")
            default_choice = "3"
        else:
            print(f"{Fore.LIGHTBLACK_EX}Continue unlocks after you approve at least one model.{Style.RESET_ALL}")
            default_choice = "1"
        choice = prompt_text("Choose action", default=default_choice)

        if choice == "1":
            provider_key = choose_provider(selected)
            if provider_key is None:
                if selected:
                    break
                print(f"{Fore.RED}Select at least one model.{Style.RESET_ALL}")
                continue
            selected, env_updates = choose_provider_models(provider_key, selected, env_updates)
        elif choice == "2" and selected:
            print_section("Remove Model", "Choose a model to remove from the approved list.")
            for index, item in enumerate(selected, start=1):
                provider_label = PROVIDER_CATALOG[item["provider"]]["label"]
                print(f"{index}. {provider_label} / {item['model']}")
            remove = prompt_text("Model number to remove")
            if not remove.isdigit() or not (1 <= int(remove) <= len(selected)):
                print(f"{Fore.RED}Invalid choice.{Style.RESET_ALL}")
                continue
            removed = selected.pop(int(remove) - 1)
            if not any(item["provider"] == removed["provider"] for item in selected):
                env_updates.pop(removed["env_var"], None)
            print(f"{Fore.GREEN}Removed {removed['model']}.{Style.RESET_ALL}")
        elif choice == "3" and selected:
            return selected, env_updates
        else:
            print(f"{Fore.RED}Unknown action.{Style.RESET_ALL}")

    return selected, env_updates


def choose_role_assignments(selected_models: list[dict], existing_mapping: dict[str, str] | None = None) -> dict[str, str]:
    options = []
    for index, item in enumerate(selected_models, start=1):
        options.append({
            "key": str(index),
            "model": item["model"],
            "label": f"{item['label']} ({item['model']})",
        })

    existing_mapping = existing_mapping or {}
    assignments = {}
    print_section("Step 2/3 - Role Assignment", "Assign approved models to each role. Only these assignments will be used.")
    for role in TASK_ROLES:
        print(f"{Fore.WHITE}{ROLE_LABELS[role]}{Style.RESET_ALL}")
        for option in options:
            print(f"  {Fore.GREEN}{option['key']}.{Style.RESET_ALL} {option['label']}")
        default_model = existing_mapping.get(role, selected_models[0]["model"])
        default_key = next((option["key"] for option in options if option["model"] == default_model), options[0]["key"])
        chosen = prompt_choice(f"Select model for {role}", options, default_key=default_key)
        assignments[role] = chosen["model"]
        print()
    return assignments


def get_recommended_model(provider_key: str) -> dict:
    provider = PROVIDER_CATALOG[provider_key]
    for model in provider["models"]:
        if model.get("tag") == "Recommended":
            return model
    return provider["models"][0]



def choose_setup_mode() -> str:
    print_section("Setup Mode", "Choose the fast path if you want DirigentAI running in a few prompts.")
    options = [
        {"key": "1", "label": "Quick setup", "note": "One provider, one recommended model, same model everywhere."},
        {"key": "2", "label": "Advanced setup", "note": "Multiple providers, multiple models, custom role mapping."},
    ]
    for option in options:
        print(f"{Fore.GREEN}{option['key']}.{Style.RESET_ALL} {option['label']}")
        print(f"   {Fore.LIGHTBLACK_EX}{option['note']}{Style.RESET_ALL}")
    print()
    return prompt_choice("Select setup mode", options, default_key="1")["key"]



def run_quick_model_setup(existing_env: dict[str, str], existing_config: dict) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    env_updates = dict(existing_env)
    preferred_provider = None
    current_primary = existing_config.get("orchestrator", {}).get("provider")
    if current_primary in PROVIDER_CATALOG:
        preferred_provider = current_primary

    print_section("Step 1/2 - Provider", "Quick setup uses one recommended model and applies it everywhere.")
    options = []
    for provider_key, provider in PROVIDER_CATALOG.items():
        recommended = get_recommended_model(provider_key)
        options.append({
            "key": provider["key"],
            "provider": provider_key,
            "label": f"{provider['label']} - {recommended['label']}",
        })
        print(f"{Fore.GREEN}{provider['key']}.{Style.RESET_ALL} {provider['label']} [recommended]")
        print(f"   {Fore.LIGHTBLACK_EX}{recommended['label']} ({recommended['model']}){Style.RESET_ALL}")
    print()

    default_key = PROVIDER_CATALOG[preferred_provider]["key"] if preferred_provider else "1"
    selected = prompt_choice("Choose provider", options, default_key=default_key)
    provider_key = selected["provider"]
    provider = PROVIDER_CATALOG[provider_key]
    recommended = get_recommended_model(provider_key)

    print_section("Recommended Model", "Quick setup picks the provider's recommended model by default.")
    print(f"{Fore.WHITE}{provider['label']}{Style.RESET_ALL}")
    print(f"- Model: {recommended['label']} ({recommended['model']})")
    print(f"- Why: {recommended.get('note', provider.get('note', 'Recommended default'))}")
    print()

    existing_key = env_updates.get(provider["env_var"], "")
    env_updates[provider["env_var"]] = prompt_text(f"API key for {provider['label']}", existing_key)
    if not env_updates[provider["env_var"]]:
        print(f"{Fore.RED}API key is required to finish setup.{Style.RESET_ALL}")
        return run_quick_model_setup(existing_env, existing_config)

    selected_models = [build_model_entry(provider_key, recommended["model"], recommended["label"], recommended.get("note", ""))]
    role_assignments = {role: selected_models[0]["model"] for role in TASK_ROLES}
    return selected_models, env_updates, role_assignments


def build_config(selected_models: list[dict], role_assignments: dict[str, str], hide_worker_creation: bool) -> dict:
    primary = next(item for item in selected_models if item["model"] == role_assignments["dirigent"])
    return {
        "llm_policy": {
            "approved_models": [item["model"] for item in selected_models],
            "force_primary_for_all_roles": len(selected_models) == 1,
        },
        "model_mapping": role_assignments,
        "orchestrator": {
            "provider": primary["provider"],
            "model": primary["model"],
            "api_key_env": primary["env_var"],
            "temperature": 0.1,
            "max_tokens": 2048,
        },
        "workers": {
            "max_workers": 15,
            "presets": {
                "coder": {
                    "capabilities": ["terminal", "file_ops"],
                    "model": role_assignments["coding"],
                    "task_type": "coding",
                    "description": "Specialized in programming and code analysis",
                },
                "researcher": {
                    "capabilities": ["web_ops", "browser_ops", "file_ops"],
                    "model": role_assignments["research"],
                    "task_type": "research",
                    "description": "Specialized in web research, browsing, and data gathering",
                },
                "browser_researcher": {
                    "capabilities": ["browser_ops", "web_ops", "file_ops"],
                    "model": role_assignments["research"],
                    "task_type": "research",
                    "description": "Specialized in dynamic websites, login flows, and browser-driven research",
                },
                "analyzer": {
                    "capabilities": ["file_ops"],
                    "model": role_assignments["analysis"],
                    "task_type": "analysis",
                    "description": "Specialized in data analysis and processing",
                },
                "admin": {
                    "capabilities": ["terminal", "file_ops"],
                    "model": role_assignments["system"],
                    "task_type": "system",
                    "description": "Specialized in system administration",
                },
            },
            "default_model": role_assignments["system"],
        },
        "providers": deepcopy(PROVIDER_ENV_MAP),
        "security": {
            "command_blacklist": [
                "rm -rf /",
                "rm -rf /*",
                "rm -rf .",
                "rm -rf *",
                "format c:",
                "del /f /s /q",
                "shutdown",
                "reboot",
            ],
            "require_confirmation": False,
            "sandbox_mode": False,
        },
        "ui": {
            "hide_worker_creation": hide_worker_creation,
            "show_technical_details": False,
            "language": "en",
        },
    }


def normalize_current_selection(config: dict, env_data: dict[str, str]) -> list[dict]:
    approved = config.get("llm_policy", {}).get("approved_models", [])
    selected = []
    for model in approved:
        info = get_model_info(model)
        if info and env_data.get(info["env_var"]):
            selected.append(info)
    if not selected:
        orchestrator_model = config.get("orchestrator", {}).get("model")
        info = get_model_info(orchestrator_model) if orchestrator_model else None
        if info and env_data.get(info["env_var"]):
            selected.append(info)
    return selected


def print_models_summary(config: dict, env_data: dict[str, str]):
    selected = normalize_current_selection(config, env_data)
    print_section("Model Policy", "Only approved models with present API keys will be used.")
    if not selected:
        print(f"{Fore.YELLOW}No approved models with API keys configured yet.{Style.RESET_ALL}")
    else:
        approved = config.get("llm_policy", {}).get("approved_models", [])
        for model in approved:
            info = get_model_info(model)
            if not info:
                continue
            provider_label = PROVIDER_CATALOG[info["provider"]]["label"]
            key_present = "yes" if env_data.get(info["env_var"]) else "no"
            print(f"- {provider_label} | {model} | key present: {key_present}")
    print()
    mapping = config.get("model_mapping", {})
    for role in TASK_ROLES:
        print(f"- {ROLE_LABELS[role]}: {mapping.get(role, 'not set')}")
    print()


def rebuild_and_save_models(config: dict, env_data: dict[str, str], selected_models: list[dict], role_assignments: dict[str, str]):
    if not selected_models:
        raise ValueError("At least one approved model is required.")
    approved_names = {item["model"] for item in selected_models}
    cleaned_assignments = {}
    fallback = selected_models[0]["model"]
    for role in TASK_ROLES:
        assigned = role_assignments.get(role, fallback)
        cleaned_assignments[role] = assigned if assigned in approved_names else fallback
    hide_worker_creation = config.get("ui", {}).get("hide_worker_creation", True)
    telegram_token = env_data.get("TELEGRAM_BOT_TOKEN", "")
    telegram_users = env_data.get("TELEGRAM_ALLOWED_USER_IDS", "")
    new_config = build_config(selected_models, cleaned_assignments, hide_worker_creation)
    new_config["ui"]["show_technical_details"] = config.get("ui", {}).get("show_technical_details", False)
    new_config["ui"]["language"] = config.get("ui", {}).get("language", "en")
    new_config["security"] = deepcopy(config.get("security", new_config["security"]))
    new_config["workers"]["max_workers"] = config.get("workers", {}).get("max_workers", 15)
    for preset_name, preset_cfg in config.get("workers", {}).get("presets", {}).items():
        if preset_name in new_config["workers"]["presets"]:
            new_config["workers"]["presets"][preset_name]["description"] = preset_cfg.get(
                "description", new_config["workers"]["presets"][preset_name]["description"]
            )
    new_env = {key: env_data.get(key, "") for key in ENV_KEYS}
    save_all(new_config, new_env, "Model configuration saved.")
    return new_config, new_env


def print_general_summary(config: dict, env_data: dict[str, str]):
    print_section("Current Config")
    print(f"- Approved models: {', '.join(config.get('llm_policy', {}).get('approved_models', [])) or 'none'}")
    print(f"- Max workers: {config.get('workers', {}).get('max_workers', 15)}")
    print(f"- Hide worker creation: {config.get('ui', {}).get('hide_worker_creation', True)}")
    print(f"- Show technical details: {config.get('ui', {}).get('show_technical_details', False)}")
    print(f"- UI language: {config.get('ui', {}).get('language', 'en')}")
    print(f"- Require confirmation: {config.get('security', {}).get('require_confirmation', False)}")
    print(f"- Sandbox mode: {config.get('security', {}).get('sandbox_mode', False)}")
    print(f"- Telegram token set: {'yes' if env_data.get('TELEGRAM_BOT_TOKEN') else 'no'}")
    print(f"- Telegram allowed IDs: {env_data.get('TELEGRAM_ALLOWED_USER_IDS', '') or 'not set'}")
    print()


def edit_telegram_settings(config: dict, env_data: dict[str, str]):
    print_section("Telegram Settings")
    env_data["TELEGRAM_BOT_TOKEN"] = prompt_text("Telegram bot token", env_data.get("TELEGRAM_BOT_TOKEN", ""))
    env_data["TELEGRAM_ALLOWED_USER_IDS"] = prompt_text(
        "Telegram allowed user IDs (comma-separated)",
        env_data.get("TELEGRAM_ALLOWED_USER_IDS", ""),
    )
    save_all(config, env_data, "Telegram settings saved.")
    return config, env_data


def edit_ui_settings(config: dict, env_data: dict[str, str]):
    print_section("UI Settings")
    ui = config.setdefault("ui", {})
    ui["hide_worker_creation"] = prompt_yes_no("Hide worker creation messages", ui.get("hide_worker_creation", True))
    ui["show_technical_details"] = prompt_yes_no("Show technical details", ui.get("show_technical_details", False))
    ui["language"] = prompt_text("UI language", ui.get("language", "en"))
    save_all(config, env_data, "UI settings saved.")
    return config, env_data


def edit_security_settings(config: dict, env_data: dict[str, str]):
    print_section("Security Settings")
    security = config.setdefault("security", {})
    security["require_confirmation"] = prompt_yes_no(
        "Require confirmation before sensitive actions", security.get("require_confirmation", False)
    )
    security["sandbox_mode"] = prompt_yes_no("Enable sandbox mode flag", security.get("sandbox_mode", False))
    blacklist = security.get("command_blacklist", [])
    print(f"Current command blacklist: {', '.join(blacklist)}")
    if prompt_yes_no("Edit command blacklist as comma-separated list", default=False):
        raw = prompt_text("Command blacklist", ", ".join(blacklist))
        security["command_blacklist"] = [item.strip() for item in raw.split(",") if item.strip()]
    save_all(config, env_data, "Security settings saved.")
    return config, env_data


def edit_worker_settings(config: dict, env_data: dict[str, str]):
    print_section("Worker Settings")
    workers = config.setdefault("workers", {})
    workers["max_workers"] = prompt_int("Maximum workers", workers.get("max_workers", 15), minimum=1)
    selected = normalize_current_selection(config, env_data)
    if selected:
        options = [{"key": str(i), "model": item["model"], "label": item["model"]} for i, item in enumerate(selected, start=1)]
        current_default = workers.get("default_model", selected[0]["model"])
        default_key = next((item["key"] for item in options if item["model"] == current_default), options[0]["key"])
        for option in options:
            print(f"{option['key']}. {option['label']}")
        workers["default_model"] = prompt_choice("Default fallback model", options, default_key)["model"]
    for preset_name, preset_config in workers.get("presets", {}).items():
        label = preset_name.capitalize()
        preset_config["description"] = prompt_text(f"{label} description", preset_config.get("description", ""))
    save_all(config, env_data, "Worker settings saved.")
    return config, env_data


def edit_env_manager(config: dict, env_data: dict[str, str]):
    print_section("Environment Values", "Edit .env entries directly from CLI.")
    for key in ENV_KEYS:
        current = env_data.get(key, "")
        new_value = prompt_text(key, current)
        env_data[key] = new_value
    save_all(config, env_data, ".env values saved.")
    return config, env_data


def edit_advanced_section(config: dict, env_data: dict[str, str]):
    sections = ["llm_policy", "model_mapping", "orchestrator", "workers", "providers", "security", "ui"]
    print_section("Advanced YAML Editor", "Paste a whole YAML or JSON object for one section on one line.")
    for index, section in enumerate(sections, start=1):
        print(f"{index}. {section}")
    selected = prompt_text("Section number")
    if not selected.isdigit() or not (1 <= int(selected) <= len(sections)):
        print(f"{Fore.RED}Invalid choice.{Style.RESET_ALL}")
        return config, env_data
    section = sections[int(selected) - 1]
    print(yaml.safe_dump(config.get(section, {}), sort_keys=False, allow_unicode=True))
    raw = prompt_text("Paste replacement YAML/JSON object")
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print(f"{Fore.RED}Invalid YAML/JSON: {exc}{Style.RESET_ALL}")
        return config, env_data
    if not isinstance(value, dict):
        print(f"{Fore.RED}Section must be a mapping object.{Style.RESET_ALL}")
        return config, env_data
    config[section] = value
    save_all(config, env_data, f"Section '{section}' saved.")
    return load_config_file(), load_existing_env()


def run_setup():
    print_banner()
    print_section("DirigentAI Setup", "This guided setup creates .env and config/dirigent.yaml for your first run.")
    print(f"{Fore.LIGHTBLACK_EX}Recommended path: Quick setup -> doctor -> cli{Style.RESET_ALL}")
    print_section(
        "Disclaimer",
        "DirigentAI can execute terminal and file actions through AI workers. Use it only on a system you control, review output carefully, and keep API keys private.",
    )
    if not prompt_yes_no("Do you accept this risk and want to continue", default=False):
        print(f"{Fore.RED}Setup cancelled.{Style.RESET_ALL}")
        sys.exit(0)

    existing_env = load_existing_env()
    existing_config = load_config_file()
    setup_mode = choose_setup_mode()

    if setup_mode == "1":
        selected_models, env_updates, role_assignments = run_quick_model_setup(existing_env, existing_config)
        print_section("Step 2/2 - Integrations", "Leave Telegram blank if you only want the local CLI for now.")
    else:
        selected_models, env_updates = choose_models(existing_env, existing_config.get("llm_policy", {}).get("approved_models", []))
        existing_mapping = existing_config.get("model_mapping", {})
        role_assignments = choose_role_assignments(selected_models, existing_mapping)
        print_section("Step 3/3 - Integrations", "Leave Telegram blank if you only want the local CLI for now.")

    env_updates["TELEGRAM_BOT_TOKEN"] = prompt_text("Telegram bot token", default=existing_env.get("TELEGRAM_BOT_TOKEN", ""))
    env_updates["TELEGRAM_ALLOWED_USER_IDS"] = prompt_text(
        "Telegram allowed user IDs (comma-separated)",
        default=existing_env.get("TELEGRAM_ALLOWED_USER_IDS", ""),
    )

    print_section("CLI Preferences", "Keep the default unless you know you want more verbose output.")
    hide_worker_creation = prompt_yes_no("Hide worker creation messages in chat output", default=True)
    config = build_config(selected_models, role_assignments, hide_worker_creation)
    save_all(config, env_updates, "Setup complete.")
    print_section(
        "Setup Complete",
        f"Saved {ENV_PATH} and {CONFIG_PATH}.\nApproved models: {', '.join(item['model'] for item in selected_models)}\nRecommended next step: run `python main.py doctor` and then `python main.py cli`.",
    )



def run_models_manager(config: dict | None = None, env_data: dict | None = None, standalone: bool = True):
    if standalone:
        print_banner()
    config = config or load_config_file()
    env_data = env_data or load_existing_env()
    if not config:
        print(f"{Fore.YELLOW}No config found. Launching setup first.{Style.RESET_ALL}")
        run_setup()
        return load_config_file(), load_existing_env()

    while True:
        print_models_summary(config, env_data)
        print(f"{Fore.LIGHTBLACK_EX}Provider-first flow. Add providers, then choose one or more models under each.{Style.RESET_ALL}")
        print("1. Add provider and models")
        print("2. Remove approved model")
        print("3. Reassign role mappings")
        print("4. Save and exit")
        print("5. Exit without saving")
        choice = prompt_text("Choose action", default="4")

        if choice == "1":
            current = [item["model"] for item in normalize_current_selection(config, env_data)]
            selected_models, env_data = choose_models(env_data, current)
            existing_selected = normalize_current_selection(config, env_data)
            combined = {item["model"]: item for item in existing_selected}
            for item in selected_models:
                combined[item["model"]] = item
            current_mapping = config.get("model_mapping", {})
            config = build_config(list(combined.values()), {
                role: current_mapping.get(role, list(combined.values())[0]["model"])
                for role in TASK_ROLES
            }, config.get("ui", {}).get("hide_worker_creation", True))
        elif choice == "2":
            selected = normalize_current_selection(config, env_data)
            if len(selected) <= 1:
                print(f"{Fore.RED}At least one approved model must remain.{Style.RESET_ALL}")
                continue
            print_section("Remove Model")
            for index, item in enumerate(selected, start=1):
                print(f"{index}. {item['label']} ({item['model']})")
            remove = prompt_text("Select model number to remove")
            if not remove.isdigit() or not (1 <= int(remove) <= len(selected)):
                print(f"{Fore.RED}Invalid choice.{Style.RESET_ALL}")
                continue
            removed = selected.pop(int(remove) - 1)
            env_data.pop(removed["env_var"], None)
            config, env_data = rebuild_and_save_models(config, env_data, selected, config.get("model_mapping", {}))
            if standalone:
                break
        elif choice == "3":
            selected = normalize_current_selection(config, env_data)
            if not selected:
                print(f"{Fore.RED}Add at least one approved model first.{Style.RESET_ALL}")
                continue
            mapping = choose_role_assignments(selected, config.get("model_mapping", {}))
            config = build_config(selected, mapping, config.get("ui", {}).get("hide_worker_creation", True))
        elif choice == "4":
            selected = normalize_current_selection(config, env_data)
            if not selected:
                print(f"{Fore.RED}No approved models with keys configured. Nothing to save.{Style.RESET_ALL}")
                continue
            config, env_data = rebuild_and_save_models(config, env_data, selected, config.get("model_mapping", {}))
            break
        elif choice == "5":
            break
        else:
            print(f"{Fore.RED}Unknown action.{Style.RESET_ALL}")

    return config, env_data


def run_config_manager():
    print_banner()
    config = load_config_file()
    env_data = load_existing_env()
    if not config:
        print(f"{Fore.YELLOW}No config found. Launching setup first.{Style.RESET_ALL}")
        run_setup()
        return

    while True:
        print_general_summary(config, env_data)
        print("1. Models and role mapping")
        print("2. Telegram settings")
        print("3. UI settings")
        print("4. Security settings")
        print("5. Worker settings")
        print("6. Environment values (.env)")
        print("7. Advanced YAML editor")
        print("8. Exit")
        choice = prompt_text("Choose section", default="8")

        if choice == "1":
            config, env_data = run_models_manager(config, env_data, standalone=False)
        elif choice == "2":
            config, env_data = edit_telegram_settings(config, env_data)
        elif choice == "3":
            config, env_data = edit_ui_settings(config, env_data)
        elif choice == "4":
            config, env_data = edit_security_settings(config, env_data)
        elif choice == "5":
            config, env_data = edit_worker_settings(config, env_data)
        elif choice == "6":
            config, env_data = edit_env_manager(config, env_data)
        elif choice == "7":
            config, env_data = edit_advanced_section(config, env_data)
        elif choice == "8":
            break
        else:
            print(f"{Fore.RED}Unknown action.{Style.RESET_ALL}")


def print_doctor_item(status: str, label: str, detail: str):
    color_map = {
        "OK": Fore.GREEN,
        "WARN": Fore.YELLOW,
        "ERROR": Fore.RED,
        "INFO": Fore.CYAN,
        "UNTESTED": Fore.LIGHTBLACK_EX,
    }
    color = color_map.get(status, Fore.WHITE)
    print(f"{color}[{status}]{Style.RESET_ALL} {label}: {detail}")



def run_doctor():
    print_banner()
    print_section("DirigentAI Doctor", "Static diagnostics for config, model routing, and environment readiness.")

    issues = {"ERROR": 0, "WARN": 0}

    def record(status: str, label: str, detail: str):
        print_doctor_item(status, label, detail)
        if status in issues:
            issues[status] += 1

    config_exists = os.path.exists(CONFIG_PATH) or os.path.exists(LEGACY_CONFIG_PATH)
    env_exists = os.path.exists(ENV_PATH)
    record("OK" if config_exists else "ERROR", "Config file", CONFIG_PATH if os.path.exists(CONFIG_PATH) else (LEGACY_CONFIG_PATH if os.path.exists(LEGACY_CONFIG_PATH) else "missing"))
    record("OK" if env_exists else "WARN", ".env file", ENV_PATH if env_exists else "missing")

    raw_config = load_config_file()
    env_data = load_existing_env()
    if not raw_config:
        record("ERROR", "Config content", "No configuration loaded. Run `python main.py setup`.")
        print()
        print_section("Summary", f"Errors: {issues['ERROR']} | Warnings: {issues['WARN']}")
        return

    try:
        from core.config import DirigentConfig
        from core.llm.factory import LLMFactory
    except Exception as exc:
        record("ERROR", "Doctor dependencies", f"Could not import config/LLM modules: {exc}")
        print()
        print_section("Summary", f"Errors: {issues['ERROR']} | Warnings: {issues['WARN']}")
        return

    config_manager = DirigentConfig(CONFIG_PATH if os.path.exists(CONFIG_PATH) else None)

    print()
    print_section("Model Policy", "Approved models are the only models DirigentAI may use.")
    approved_models = raw_config.get("llm_policy", {}).get("approved_models", [])
    if not approved_models:
        record("ERROR", "Approved models", "No approved models configured.")
    else:
        available_models = set(config_manager.get_available_models())
        providers_config = raw_config.get("providers", {})
        for model in approved_models:
            provider = LLMFactory.infer_provider_from_model(model) or infer_provider_from_model(model)
            env_var = providers_config.get(provider, {}).get("api_key_env") if provider else None
            env_var = env_var or PROVIDER_ENV_MAP.get(provider, {}).get("api_key_env") if provider else None
            normalized = LLMFactory.normalize_model_string(model, provider)
            key_present = bool(env_var and (env_data.get(env_var) or os.getenv(env_var)))
            curated = model in MODEL_BY_NAME

            if not provider:
                record("WARN", model, "Provider could not be inferred. Treating as custom/unknown risk.")
                continue

            status = "OK" if key_present else "UNTESTED"
            if model not in available_models:
                status = "WARN" if key_present else "UNTESTED"
            details = [f"provider={provider}"]
            if env_var:
                details.append(f"env={env_var}")
                details.append(f"key={'yes' if key_present else 'no'}")
            details.append(f"normalized={normalized}")
            details.append("curated=yes" if curated else "curated=no (custom/legacy)")
            if model not in available_models:
                details.append("not currently available under llm_policy")
            record(status, model, " | ".join(details))

    print()
    print_section("Routing", "How models resolve for the orchestrator and worker task roles.")
    orchestrator_cfg = raw_config.get("orchestrator", {})
    orchestrator_model = orchestrator_cfg.get("model")
    orchestrator_provider = orchestrator_cfg.get("provider") or (LLMFactory.infer_provider_from_model(orchestrator_model) if orchestrator_model else None)
    if orchestrator_model:
        normalized = LLMFactory.normalize_model_string(orchestrator_model, orchestrator_provider)
        record("OK", "Orchestrator", f"provider={orchestrator_provider or 'unknown'} | model={orchestrator_model} | normalized={normalized}")
    else:
        record("ERROR", "Orchestrator", "No orchestrator model configured.")

    mapping = raw_config.get("model_mapping", {})
    approved_set = set(approved_models)
    for role in TASK_ROLES:
        assigned = mapping.get(role)
        if not assigned:
            record("ERROR", f"Role {role}", "No model assigned.")
            continue
        resolved = config_manager.get_model_for_task(role)
        status = "OK" if assigned in approved_set else "WARN"
        detail = f"assigned={assigned} | resolved={resolved}"
        if assigned not in approved_set:
            detail += " | assigned model is not in approved_models"
        record(status, f"Role {role}", detail)

    print()
    print_section("Workers", "Preset worker models after policy resolution.")
    workers_cfg = config_manager.get_workers_config()
    for preset_name, preset_cfg in workers_cfg.get("presets", {}).items():
        task_type = preset_cfg.get("task_type", "unknown")
        model = preset_cfg.get("model", "unset")
        capabilities = ", ".join(preset_cfg.get("capabilities", [])) or "none"
        status = "OK" if model in config_manager.get_available_models() else "WARN"
        record(status, f"Preset {preset_name}", f"task_type={task_type} | model={model} | capabilities={capabilities}")

    print()
    print_section("Environment", "Presence checks only. No live API requests are sent.")
    for key in ENV_KEYS:
        if key.startswith("TELEGRAM"):
            status = "OK" if env_data.get(key) else "UNTESTED"
            detail = "configured" if env_data.get(key) else "not set"
        else:
            used = any(item.get("env_var") == key for item in MODEL_BY_NAME.values()) or key == "DEEPSEEK_API_KEY"
            if not used:
                continue
            status = "OK" if env_data.get(key) else "UNTESTED"
            detail = "configured" if env_data.get(key) else "not set"
        record(status, key, detail)

    print()
    print_section(
        "Summary",
        f"Errors: {issues['ERROR']} | Warnings: {issues['WARN']}\n`doctor` is static validation only. Models without keys are marked UNTESTED rather than OK.",
    )


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.settimeout(0.5)
        return handle.connect_ex(("127.0.0.1", port)) == 0


def start_component(script_name: str, label: str, hidden: bool = True):
    print(f"{Fore.CYAN}[System]{Style.RESET_ALL} Starting {label}...")
    flags = 0
    if hidden and os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen([sys.executable, script_name], creationflags=flags)
    processes.append(proc)
    return proc


def cleanup(sig=None, frame=None):
    print(f"\n{Fore.RED}[System]{Style.RESET_ALL} Terminating all components...")
    for proc in processes:
        try:
            proc.terminate()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)


def run_base(with_cli: bool = False):
    print_banner()
    if not is_port_in_use(8888):
        start_component("hub.py", "Hub Engine")
        for _ in range(10):
            if is_port_in_use(8888):
                break
            time.sleep(1)
    else:
        print(f"{Fore.GREEN}[System]{Style.RESET_ALL} Hub Engine already running.")

    load_dotenv(override=True)
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        start_component("telegram_client.py", "Telegram Bridge")
    else:
        print(f"{Fore.YELLOW}[System]{Style.RESET_ALL} Telegram not configured, skipping.")

    if with_cli:
        print(f"{Fore.YELLOW}[System]{Style.RESET_ALL} Opening CLI interface...")
        try:
            subprocess.run([sys.executable, "app.py"])
        finally:
            cleanup()
    else:
        print(f"\n{Fore.GREEN}[System]{Style.RESET_ALL} Firm is ONLINE (Hub + optional Telegram).")
        print(f"{Fore.WHITE}Press Ctrl+C to exit.{Style.RESET_ALL}\n")
        while True:
            time.sleep(60)


def print_usage():
    print("Usage: python main.py [setup|config|models|doctor|cli|onboard]")


if __name__ == "__main__":
    command = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    if not os.path.exists(ENV_PATH) and command not in {"setup", "onboard", "models", "config"}:
        print(f"{Fore.YELLOW}No .env found. Launching setup first.{Style.RESET_ALL}")
        run_setup()
        if command == "":
            sys.exit(0)

    if command in {"setup", "onboard"}:
        run_setup()
    elif command == "models":
        run_models_manager()
    elif command == "config":
        run_config_manager()
    elif command == "doctor":
        run_doctor()
    elif command == "cli":
        run_base(with_cli=True)
    elif command == "":
        run_base(with_cli=False)
    else:
        print_usage()
