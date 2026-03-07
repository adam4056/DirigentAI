import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import requests

from core.llm.factory import LLMFactory
from tools.browser import HeadlessBrowserManager

logger = logging.getLogger("dirigent.worker")

WORKSPACE_ROOT = Path.cwd().resolve()
CURRENT_OS = platform.system().lower()


def normalize_path_for_comparison(path: Path) -> Path:
    """Normalize Windows extended-length paths so relative checks stay stable."""
    resolved = path.resolve()
    resolved_str = str(resolved)
    windows_extended_prefix = chr(92) + chr(92) + "?" + chr(92)
    if resolved_str.startswith(windows_extended_prefix):
        return Path(resolved_str[len(windows_extended_prefix):])
    return resolved

COMMON_COMMAND_BLACKLIST = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf .",
    "rm -rf *",
    "rm -rf ./",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init 0",
    "init 6",
    ">()",
    "wget",
    "curl -o",
    "curl -O",
    "curl -L",
    "chmod 777",
    "chmod -R 777",
    "chown -R",
    "systemctl stop",
    "systemctl disable",
    "service stop",
    "pkill -9",
    "kill -9",
    "killall",
    "pip uninstall -y",
    "npm uninstall",
]

WINDOWS_COMMAND_BLACKLIST = [
    "format c:",
    "del /f /s /q c:",
    "del /f /s /q *",
    "del *.*",
    "rd /s /q",
    "reg delete",
    "reg add",
    "net user",
    "net localgroup",
    "taskkill /f /im",
    "taskkill /f /t",
]

UNIX_COMMAND_BLACKLIST = [
    "> /dev/sd",
    "mkfs.",
    "dd if=/dev",
]

COMMON_PATTERN_BLACKLIST = [
    "rm -rf /",
    "rm -rf *",
    "rm -rf .",
    "mkfs.",
    "dd if=/dev",
    "chmod 777",
    "chown -R",
    "systemctl stop",
    "systemctl disable",
    "service stop",
    "pkill -9",
    "kill -9",
    "killall",
    "pip uninstall",
    "npm uninstall",
    ":(){",
    "|:&};",
]

WINDOWS_PATTERN_BLACKLIST = [
    "format c:",
    "del /f /s /q c:",
    "del /f /s /q *",
    "reg delete",
    "reg add",
    "net user",
    "net localgroup",
    "taskkill /f",
]

SENSITIVE_PATH_PATTERNS = [
    ".env",
    ".git/config",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "shadow",
    "passwd",
    "authorized_keys",
]


def get_platform_label() -> str:
    if CURRENT_OS.startswith("win"):
        return "windows"
    if CURRENT_OS == "darwin":
        return "macos"
    if CURRENT_OS == "linux":
        return "linux"
    return CURRENT_OS or "unknown"


def get_shell_command() -> tuple[list[str], str]:
    if get_platform_label() == "windows":
        for candidate in ("pwsh", "powershell"):
            path = shutil.which(candidate)
            if path:
                return [path, "-NoProfile", "-Command"], Path(path).name
        return ["cmd.exe", "/C"], "cmd.exe"

    for candidate in ("bash", "zsh", "sh"):
        path = shutil.which(candidate)
        if path:
            return [path, "-lc"], Path(path).name
    return ["/bin/sh", "-lc"], "/bin/sh"


def get_command_blacklist() -> list[str]:
    blocked = list(COMMON_COMMAND_BLACKLIST)
    if get_platform_label() == "windows":
        blocked.extend(WINDOWS_COMMAND_BLACKLIST)
    else:
        blocked.extend(UNIX_COMMAND_BLACKLIST)
    return blocked


def get_pattern_blacklist() -> list[str]:
    patterns = list(COMMON_PATTERN_BLACKLIST)
    if get_platform_label() == "windows":
        patterns.extend(WINDOWS_PATTERN_BLACKLIST)
    return patterns


def is_command_safe(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower().strip()
    for blocked in get_command_blacklist():
        if blocked.lower() in cmd_lower:
            return False, f"Blocked command pattern: '{blocked}'"
    for pattern in get_pattern_blacklist():
        if pattern.lower() in cmd_lower:
            return False, f"Blocked dangerous pattern: '{pattern}'"
    return True, "OK"


def is_path_safe(filepath: str) -> tuple[bool, str]:
    try:
        resolved = normalize_path_for_comparison(Path(filepath))
        workspace_root = normalize_path_for_comparison(WORKSPACE_ROOT)
        try:
            resolved.relative_to(workspace_root)
        except ValueError:
            return False, (
                f"Path '{filepath}' resolves to '{resolved}' which is outside "
                f"the allowed workspace '{workspace_root}'"
            )

        resolved_lower = str(resolved).lower()
        for pattern in SENSITIVE_PATH_PATTERNS:
            if pattern == ".env" and resolved.name == ".env":
                return False, f"Access to sensitive file '{pattern}' is forbidden."
            if pattern != ".env" and pattern in resolved_lower:
                return False, f"Access to sensitive path pattern '{pattern}' is forbidden."
        return True, "OK"
    except Exception as exc:
        return False, f"Path validation error: {exc}"


class Worker:
    """An AI-powered worker agent with capability-gated tools."""

    MAX_FUNCTION_CALL_ITERATIONS = 8

    def __init__(
        self,
        worker_id: str,
        capabilities: list[str] | None = None,
        description: str = "",
        api_key: str | None = None,
        model: str | None = None,
        model_name: str = "gemini-3-flash-preview",
        provider: str = "gemini",
        llm_client=None,
    ):
        self.worker_id = worker_id
        self.capabilities = capabilities or ["terminal", "file_ops"]
        self.description = description
        self.api_key = api_key
        self.model = model or model_name
        self.provider = provider
        self.browser_manager: HeadlessBrowserManager | None = None
        self.platform_name = get_platform_label()
        self.shell_cmd, self.shell_name = get_shell_command()

        if llm_client:
            self.llm_client = llm_client
        else:
            try:
                self.llm_client = LLMFactory.create_client_from_model(
                    model=self.model,
                    api_key=api_key,
                    provider=self.provider,
                )
            except Exception as exc:
                logger.warning(f"Failed to create LLM client for worker {worker_id}: {exc}")
                self.llm_client = None

    def __del__(self):
        if self.browser_manager:
            try:
                self.browser_manager.shutdown()
            except Exception:
                pass

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "capabilities": self.capabilities,
            "description": self.description,
            "model": self.model,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        api_key: str | None = None,
        provider: str = "gemini",
        model_name: str = "gemini-3-flash-preview",
    ) -> "Worker":
        model = data.get("model", model_name)
        capabilities = data.get("capabilities", [])
        description = data.get("description", "")
        if model != model_name or "model" in data:
            return cls(
                worker_id=data["worker_id"],
                capabilities=capabilities,
                description=description,
                api_key=api_key,
                model=model,
            )
        return cls(
            worker_id=data["worker_id"],
            capabilities=capabilities,
            description=description,
            api_key=api_key,
            provider=provider,
            model_name=model_name,
        )

    def execute(self, instruction: str) -> str:
        if not self.llm_client:
            return f"Worker {self.worker_id}: AI brain missing (API key)."

        logger.info(f"[{self.worker_id}] Thinking: {instruction[:80]}...")
        worker_tools = self._build_tool_definitions()
        system_prompt = f"""
You are specialized worker {self.worker_id}. Your description: {self.description}.
Your capabilities (permissions): {self.capabilities}.
Available tools: {[t['name'] for t in worker_tools] if worker_tools else 'none'}.
Runtime platform: {self.platform_name}.
Default shell for terminal commands: {self.shell_name}.
Workspace root: {WORKSPACE_ROOT}.

Your boss (DirigentAI) assigned you a task: "{instruction}"

If the task involves a dynamic website, login flow, or JavaScript-heavy interaction and you have browser tools, prefer browser tools over plain fetches.
When using terminal commands, write commands that match the runtime platform.
Always work within your permissions. Keep output concise and technical.
Language: English.
"""
        messages: List[Dict[str, Any]] = [{"role": "user", "content": instruction}]

        try:
            iterations = 0
            while iterations < self.MAX_FUNCTION_CALL_ITERATIONS:
                iterations += 1
                response = self.llm_client.generate_content(
                    system_instruction=system_prompt,
                    messages=messages,
                    tools=worker_tools,
                    tool_choice="auto" if worker_tools else "none",
                )

                response_text = response.get("text", "")
                tool_calls = response.get("tool_calls", [])

                if not tool_calls:
                    if response_text:
                        messages.append({"role": "assistant", "content": response_text})
                    return response_text or "No response generated."

                assistant_tool_calls = []
                tool_results = []
                for tool_call in tool_calls:
                    tool_call_id = tool_call.get("id") or f"call_{tool_call.get('name', 'tool')}"
                    fn_name = tool_call.get("name")
                    args = tool_call.get("args", {})
                    logger.debug(f"[{self.worker_id}] Tool call: {fn_name}({args})")
                    result = self._dispatch_tool(fn_name, args)
                    assistant_tool_calls.append({"id": tool_call_id, "name": fn_name, "args": args})
                    tool_results.append({"tool_call_id": tool_call_id, "name": fn_name, "result": result})

                messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "tool_calls": assistant_tool_calls,
                })
                for tool_result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_result["tool_call_id"],
                        "name": tool_result["name"],
                        "content": str(tool_result["result"]),
                    })

            logger.warning(f"[{self.worker_id}] Hit max iterations ({self.MAX_FUNCTION_CALL_ITERATIONS})")
            return f"Worker {self.worker_id}: Reached maximum tool call limit."
        except Exception as exc:
            logger.error(f"[{self.worker_id}] Error: {exc}")
            return f"Worker {self.worker_id} Error: {exc}"

    def _build_tool_definitions(self) -> list[dict]:
        worker_tools: list[dict] = []

        if "terminal" in self.capabilities:
            worker_tools.append(
                {
                    "name": "run_terminal_command",
                    "description": "Runs a command in the platform shell. Dangerous commands are blocked for safety.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string", "description": "The command to run."}},
                        "required": ["command"],
                    },
                }
            )

        if "file_ops" in self.capabilities:
            worker_tools.extend([
                {
                    "name": "write_to_file",
                    "description": "Writes text to a file within the workspace directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {"filename": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["filename", "content"],
                    },
                },
                {
                    "name": "read_file",
                    "description": "Reads file content from within the workspace directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {"filename": {"type": "string"}},
                        "required": ["filename"],
                    },
                },
                {
                    "name": "list_directory",
                    "description": "Lists files in a directory within the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "Directory path (default '.')"}},
                    },
                },
            ])

        if "web_ops" in self.capabilities:
            worker_tools.append(
                {
                    "name": "fetch_url",
                    "description": "Downloads text content from a given URL. Best for static pages or APIs.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                }
            )

        if "browser_ops" in self.capabilities:
            worker_tools.extend([
                {
                    "name": "browser_navigate",
                    "description": "Open a page in a persistent headless browser session with JavaScript, cookies, and login support.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "session_id": {"type": "string", "description": "Optional browser session id.", "default": "default"},
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "browser_click",
                    "description": "Click an element in a persistent browser session using a CSS selector.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string"},
                            "session_id": {"type": "string", "default": "default"},
                        },
                        "required": ["selector"],
                    },
                },
                {
                    "name": "browser_type",
                    "description": "Type text into a field in a persistent browser session. Useful for login flows and search forms.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string"},
                            "text": {"type": "string"},
                            "session_id": {"type": "string", "default": "default"},
                            "press_enter": {"type": "boolean"},
                            "clear_first": {"type": "boolean"},
                        },
                        "required": ["selector", "text"],
                    },
                },
                {
                    "name": "browser_wait",
                    "description": "Wait for a selector, network idle, or a simple timeout inside the browser session.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "default": "default"},
                            "selector": {"type": "string"},
                            "timeout_ms": {"type": "integer"},
                            "wait_for_network_idle": {"type": "boolean"},
                        },
                    },
                },
                {
                    "name": "browser_extract_text",
                    "description": "Extract cleaned, model-friendly text from the current page in the browser session.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "default": "default"},
                            "max_chars": {"type": "integer"},
                        },
                    },
                },
                {
                    "name": "browser_list_links",
                    "description": "List visible links from the current page in the browser session.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "default": "default"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
                {
                    "name": "browser_close",
                    "description": "Close a persistent browser session and clear its cookies and page state.",
                    "parameters": {
                        "type": "object",
                        "properties": {"session_id": {"type": "string", "default": "default"}},
                    },
                },
            ])

        return worker_tools

    def _dispatch_tool(self, fn_name: str, args: dict) -> str:
        if fn_name == "run_terminal_command":
            return self.run_terminal(args.get("command", ""))
        if fn_name == "write_to_file":
            return self.do_write_file(args.get("filename", ""), args.get("content", ""))
        if fn_name == "read_file":
            return self.do_read_file(args.get("filename", ""))
        if fn_name == "list_directory":
            return self.do_list_directory(args.get("path", "."))
        if fn_name == "fetch_url":
            return self.do_web_fetch(args.get("url", ""))
        if fn_name == "browser_navigate":
            return self.browser_navigate(args.get("url", ""), args.get("session_id", "default"))
        if fn_name == "browser_click":
            return self.browser_click(args.get("selector", ""), args.get("session_id", "default"))
        if fn_name == "browser_type":
            return self.browser_type(
                args.get("selector", ""),
                args.get("text", ""),
                args.get("session_id", "default"),
                args.get("press_enter", False),
                args.get("clear_first", True),
            )
        if fn_name == "browser_wait":
            return self.browser_wait(
                args.get("session_id", "default"),
                args.get("selector", ""),
                args.get("timeout_ms", 5000),
                args.get("wait_for_network_idle", False),
            )
        if fn_name == "browser_extract_text":
            return self.browser_extract_text(args.get("session_id", "default"), args.get("max_chars", 8000))
        if fn_name == "browser_list_links":
            return self.browser_list_links(args.get("session_id", "default"), args.get("limit", 50))
        if fn_name == "browser_close":
            return self.browser_close(args.get("session_id", "default"))
        return f"Error: Unknown tool '{fn_name}'."

    def _get_browser_manager(self) -> HeadlessBrowserManager:
        if self.browser_manager is None:
            self.browser_manager = HeadlessBrowserManager()
        return self.browser_manager

    def run_terminal(self, command: str) -> str:
        is_safe, reason = is_command_safe(command)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked command: {command} ({reason})")
            return f"Security: Command blocked. {reason}"

        try:
            completed = subprocess.run(
                [*self.shell_cmd, command],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(WORKSPACE_ROOT),
            )
            output = completed.stdout if completed.returncode == 0 else completed.stderr
            return (
                f"Platform={self.platform_name} | shell={self.shell_name} | exit={completed.returncode}\n"
                f"{output}"
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after 15 seconds on {self.platform_name}."
        except FileNotFoundError as exc:
            return f"Error: Shell not available on {self.platform_name}: {exc}"
        except Exception as exc:
            return f"Error: {exc}"

    def do_write_file(self, filename: str, content: str) -> str:
        is_safe, reason = is_path_safe(filename)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked file write: {filename} ({reason})")
            return f"Security: {reason}"
        try:
            filepath = Path(filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            return f"OK: {filename} written ({len(content)} chars)."
        except Exception as exc:
            return f"Error writing file: {exc}"

    def do_read_file(self, filename: str) -> str:
        is_safe, reason = is_path_safe(filename)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked file read: {filename} ({reason})")
            return f"Security: {reason}"
        try:
            return Path(filename).read_text(encoding="utf-8")
        except Exception as exc:
            return f"Error reading file: {exc}"

    def do_list_directory(self, path: str = ".") -> str:
        is_safe, reason = is_path_safe(path)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked dir list: {path} ({reason})")
            return f"Security: {reason}"
        try:
            target = Path(path)
            return str(sorted(item.name for item in target.iterdir()))
        except Exception as exc:
            return f"Error listing directory: {exc}"

    def do_web_fetch(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text[:2000]
        except requests.RequestException as exc:
            return f"Web Error: {exc}"

    def browser_navigate(self, url: str, session_id: str = "default") -> str:
        try:
            return self._get_browser_manager().navigate(url=url, session_id=session_id)
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_click(self, selector: str, session_id: str = "default") -> str:
        try:
            return self._get_browser_manager().click(selector=selector, session_id=session_id)
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_type(
        self,
        selector: str,
        text: str,
        session_id: str = "default",
        press_enter: bool = False,
        clear_first: bool = True,
    ) -> str:
        try:
            return self._get_browser_manager().type_text(
                selector=selector,
                text=text,
                session_id=session_id,
                press_enter=press_enter,
                clear_first=clear_first,
            )
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_wait(
        self,
        session_id: str = "default",
        selector: str = "",
        timeout_ms: int = 5000,
        wait_for_network_idle: bool = False,
    ) -> str:
        try:
            return self._get_browser_manager().wait(
                session_id=session_id,
                selector=selector,
                timeout_ms=timeout_ms,
                wait_for_network_idle=wait_for_network_idle,
            )
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_extract_text(self, session_id: str = "default", max_chars: int = 8000) -> str:
        try:
            return self._get_browser_manager().extract_text(session_id=session_id, max_chars=max_chars)
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_list_links(self, session_id: str = "default", limit: int = 50) -> str:
        try:
            return self._get_browser_manager().list_links(session_id=session_id, limit=limit)
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_close(self, session_id: str = "default") -> str:
        try:
            return self._get_browser_manager().close(session_id=session_id)
        except Exception as exc:
            return f"Browser Error: {exc}"
