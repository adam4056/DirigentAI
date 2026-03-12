import logging
import os
import platform
import shutil
import subprocess
import zipfile
import tarfile
import difflib
import re
import glob
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                {
                    "name": "batch_process_files",
                    "description": "Batch process multiple files: apply operation (read, write, copy, move) to multiple files matching pattern.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string", "enum": ["read", "copy", "move", "delete"], "description": "Operation to perform"},
                            "source_pattern": {"type": "string", "description": "Glob pattern for source files"},
                            "target_dir": {"type": "string", "description": "Target directory for copy/move (optional)"},
                            "content": {"type": "string", "description": "Content to write (for write operation)"},
                        },
                        "required": ["operation", "source_pattern"],
                    },
                },
                {
                    "name": "search_files",
                    "description": "Search files by content across directories. Supports text search with regex.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_text": {"type": "string", "description": "Text or regex pattern to search for"},
                            "directory": {"type": "string", "description": "Directory to search in (default '.')"},
                            "file_pattern": {"type": "string", "description": "Glob pattern for files (e.g., '*.txt')"},
                            "case_sensitive": {"type": "boolean", "description": "Case-sensitive search (default false)"},
                        },
                        "required": ["search_text"],
                    },
                },
                {
                    "name": "compare_files",
                    "description": "Compare two files and show differences (diff).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file1": {"type": "string", "description": "First file path"},
                            "file2": {"type": "string", "description": "Second file path"},
                            "context_lines": {"type": "integer", "description": "Number of context lines in diff (default 3)"},
                        },
                        "required": ["file1", "file2"],
                    },
                },
                {
                    "name": "extract_archive",
                    "description": "Extract ZIP/RAR/TAR archive to directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "archive_path": {"type": "string", "description": "Path to archive file"},
                            "extract_dir": {"type": "string", "description": "Directory to extract to (optional)"},
                        },
                        "required": ["archive_path"],
                    },
                },
                {
                    "name": "create_archive",
                    "description": "Create ZIP/TAR archive from files or directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_path": {"type": "string", "description": "File, directory, or glob pattern to archive"},
                            "archive_path": {"type": "string", "description": "Output archive path"},
                            "archive_type": {"type": "string", "enum": ["zip", "tar"], "description": "Archive format (default zip)"},
                        },
                        "required": ["source_path", "archive_path"],
                    },
                },
            ])

        if "web_ops" in self.capabilities:
            worker_tools.extend([
                {
                    "name": "fetch_url",
                    "description": "Downloads text content from a given URL. Best for static pages or APIs.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
                {
                    "name": "fetch_api",
                    "description": "Make API calls with custom methods, headers, and body. Supports GET, POST, PUT, DELETE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
                            "headers": {"type": "object", "description": "HTTP headers as key-value pairs"},
                            "body": {"type": "string", "description": "Request body (for POST, PUT, PATCH)"},
                            "params": {"type": "object", "description": "Query parameters"},
                        },
                        "required": ["url"],
                    },
                },
            ])

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
                    "name": "browser_extract_data",
                    "description": "Extract structured data from webpage using CSS selectors. Returns JSON data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "default": "default"},
                            "selectors": {"type": "object", "description": "Dictionary mapping keys to CSS selectors"},
                            "as_table": {"type": "boolean", "description": "Extract table data if selector matches table"},
                        },
                        "required": ["selectors"],
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

        if "dev_tools" in self.capabilities:
            worker_tools.extend([
                {
                    "name": "execute_code",
                    "description": "Execute code snippet in specified language (python, javascript, shell). Runs in isolated subprocess with timeout.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "language": {"type": "string", "enum": ["python", "javascript", "shell", "bash"], "description": "Programming language"},
                            "code": {"type": "string", "description": "Code to execute"},
                            "timeout_seconds": {"type": "integer", "description": "Timeout in seconds (default 10)"},
                            "args": {"type": "array", "items": {"type": "string"}, "description": "Command line arguments"},
                        },
                        "required": ["language", "code"],
                    },
                },
                {
                    "name": "git_status",
                    "description": "Get git repository status (status, diff, log).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string", "enum": ["status", "diff", "log", "branch"], "description": "Git operation"},
                            "path": {"type": "string", "description": "Repository path (default '.')"},
                            "limit": {"type": "integer", "description": "Limit output lines"},
                        },
                        "required": ["operation"],
                    },
                },
                {
                    "name": "run_dependency_command",
                    "description": "Run dependency management command (pip, npm, poetry, etc.).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "enum": ["pip", "npm", "yarn", "poetry", "cargo"], "description": "Dependency tool"},
                            "command": {"type": "string", "description": "Command (install, update, list, etc.)"},
                            "package": {"type": "string", "description": "Package name (optional)"},
                            "path": {"type": "string", "description": "Working directory (default '.')"},
                        },
                        "required": ["tool", "command"],
                    },
                },
                {
                    "name": "run_tests",
                    "description": "Run test suite (pytest, unittest, jest, etc.).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "framework": {"type": "string", "enum": ["pytest", "unittest", "jest", "mocha"], "description": "Testing framework"},
                            "path": {"type": "string", "description": "Test directory or file (default '.')"},
                            "args": {"type": "string", "description": "Additional arguments"},
                        },
                        "required": ["framework"],
                    },
                },
            ])

        if "monitoring_ops" in self.capabilities:
            worker_tools.extend([
                {
                    "name": "system_resource_stats",
                    "description": "Get system resource statistics (CPU, memory, disk usage).",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "list_processes",
                    "description": "List running processes with optional filtering.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filter": {"type": "string", "description": "Filter process name or command"},
                            "limit": {"type": "integer", "description": "Maximum number of processes to list"},
                        },
                    },
                },
                {
                    "name": "kill_process",
                    "description": "Terminate a process by PID (with safety checks).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pid": {"type": "integer", "description": "Process ID"},
                            "signal": {"type": "string", "enum": ["SIGTERM", "SIGKILL"], "default": "SIGTERM"},
                        },
                        "required": ["pid"],
                    },
                },
                {
                    "name": "tail_log",
                    "description": "Tail a log file (last N lines).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {"type": "string", "description": "Path to log file"},
                            "lines": {"type": "integer", "description": "Number of lines to tail (default 50)"},
                            "follow": {"type": "boolean", "description": "Follow live updates (default false)"},
                        },
                        "required": ["filepath"],
                    },
                },
                {
                    "name": "analyze_logs",
                    "description": "Search logs for patterns and produce summary.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {"type": "string", "description": "Path to log file"},
                            "pattern": {"type": "string", "description": "Search pattern (regex)"},
                            "hours": {"type": "integer", "description": "Analyze last N hours"},
                        },
                        "required": ["filepath", "pattern"],
                    },
                },
                {
                    "name": "create_backup",
                    "description": "Create timestamped backup of files or directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_path": {"type": "string", "description": "File or directory to backup"},
                            "backup_dir": {"type": "string", "description": "Backup directory (optional)"},
                            "compression": {"type": "string", "enum": ["zip", "tar.gz"], "default": "zip"},
                        },
                        "required": ["source_path"],
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
        if fn_name == "batch_process_files":
            return self.batch_process_files(
                args.get("operation", ""),
                args.get("source_pattern", ""),
                args.get("target_dir", ""),
                args.get("content", ""),
            )
        if fn_name == "search_files":
            return self.search_files(
                args.get("search_text", ""),
                args.get("directory", "."),
                args.get("file_pattern", ""),
                args.get("case_sensitive", False),
            )
        if fn_name == "compare_files":
            return self.compare_files(
                args.get("file1", ""),
                args.get("file2", ""),
                args.get("context_lines", 3),
            )
        if fn_name == "extract_archive":
            return self.extract_archive(
                args.get("archive_path", ""),
                args.get("extract_dir", ""),
            )
        if fn_name == "create_archive":
            return self.create_archive(
                args.get("source_path", ""),
                args.get("archive_path", ""),
                args.get("archive_type", "zip"),
            )
        if fn_name == "fetch_url":
            return self.do_web_fetch(args.get("url", ""))
        if fn_name == "fetch_api":
            return self.do_api_call(
                args.get("url", ""),
                args.get("method", "GET"),
                args.get("headers", {}),
                args.get("body", ""),
                args.get("params", {}),
            )
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
        if fn_name == "browser_extract_data":
            return self.browser_extract_data(
                args.get("session_id", "default"),
                args.get("selectors", {}),
                args.get("as_table", False),
            )
        if fn_name == "browser_close":
            return self.browser_close(args.get("session_id", "default"))
        if fn_name == "execute_code":
            return self.execute_code(
                args.get("language", ""),
                args.get("code", ""),
                args.get("timeout_seconds", 10),
                args.get("args", []),
            )
        if fn_name == "git_status":
            return self.git_status(
                args.get("operation", ""),
                args.get("path", "."),
                args.get("limit", 100),
            )
        if fn_name == "run_dependency_command":
            return self.run_dependency_command(
                args.get("tool", ""),
                args.get("command", ""),
                args.get("package", ""),
                args.get("path", "."),
            )
        if fn_name == "run_tests":
            return self.run_tests(
                args.get("framework", ""),
                args.get("path", "."),
                args.get("args", ""),
            )
        if fn_name == "system_resource_stats":
            return self.system_resource_stats()
        if fn_name == "list_processes":
            return self.list_processes(
                args.get("filter", ""),
                args.get("limit", 50),
            )
        if fn_name == "kill_process":
            return self.kill_process(
                args.get("pid", 0),
                args.get("signal", "SIGTERM"),
            )
        if fn_name == "tail_log":
            return self.tail_log(
                args.get("filepath", ""),
                args.get("lines", 50),
                args.get("follow", False),
            )
        if fn_name == "analyze_logs":
            return self.analyze_logs(
                args.get("filepath", ""),
                args.get("pattern", ""),
                args.get("hours", 24),
            )
        if fn_name == "create_backup":
            return self.create_backup(
                args.get("source_path", ""),
                args.get("backup_dir", ""),
                args.get("compression", "zip"),
            )
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

    def do_api_call(self, url: str, method: str = "GET", headers: Optional[dict] = None, body: str = "", params: Optional[dict] = None) -> str:
        """Make API call with custom method, headers, and body."""
        try:
            if headers is None:
                headers = {}
            if params is None:
                params = {}
            
            # Basic safety check: allow only http/https URLs
            if not url.startswith(('http://', 'https://')):
                return f"Error: URL must start with http:// or https://"
            
            # Prepare request
            request_kwargs = {
                'url': url,
                'headers': headers,
                'params': params,
                'timeout': 30,
            }
            
            if method.upper() in ['POST', 'PUT', 'PATCH', 'DELETE'] and body:
                request_kwargs['data'] = body
            
            # Make request
            response = requests.request(method.upper(), **request_kwargs)
            
            # Format response
            result = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'body': response.text[:5000],
            }
            
            return f"API Response ({response.status_code}):\n{result['body']}"
        
        except requests.RequestException as exc:
            return f"API Error: {exc}"
        except Exception as exc:
            return f"Error in API call: {exc}"

    def batch_process_files(self, operation: str, source_pattern: str, target_dir: str = "", content: str = "") -> str:
        """Batch process files matching glob pattern."""
        try:
            # Find files matching pattern
            matches = list(Path().glob(source_pattern))
            if not matches:
                return f"No files found matching pattern: {source_pattern}"
            
            results = []
            for filepath in matches:
                # Check path safety
                is_safe, reason = is_path_safe(str(filepath))
                if not is_safe:
                    results.append(f"SKIP {filepath}: {reason}")
                    continue
                
                if operation == "read":
                    try:
                        file_content = filepath.read_text(encoding="utf-8")[:1000]
                        results.append(f"READ {filepath}: {len(file_content)} chars")
                    except Exception as e:
                        results.append(f"READ {filepath}: ERROR {e}")
                
                elif operation == "copy":
                    if not target_dir:
                        return "Error: target_dir required for copy operation"
                    target_path = Path(target_dir) / filepath.name
                    is_safe_target, reason_target = is_path_safe(str(target_path))
                    if not is_safe_target:
                        results.append(f"SKIP copy {filepath}: target unsafe - {reason_target}")
                        continue
                    shutil.copy2(filepath, target_path)
                    results.append(f"COPY {filepath} -> {target_path}")
                
                elif operation == "move":
                    if not target_dir:
                        return "Error: target_dir required for move operation"
                    target_path = Path(target_dir) / filepath.name
                    is_safe_target, reason_target = is_path_safe(str(target_path))
                    if not is_safe_target:
                        results.append(f"SKIP move {filepath}: target unsafe - {reason_target}")
                        continue
                    shutil.move(str(filepath), str(target_path))
                    results.append(f"MOVE {filepath} -> {target_path}")
                
                elif operation == "delete":
                    # Extra safety: confirm not deleting too many files at once
                    if len(matches) > 10:
                        return "Error: Cannot delete more than 10 files at once for safety"
                    filepath.unlink()
                    results.append(f"DELETE {filepath}")
                
                else:
                    return f"Error: Unknown operation '{operation}'. Use read/copy/move/delete."
            
            return f"Batch processed {len(matches)} files:\n" + "\n".join(results)
        
        except Exception as exc:
            return f"Error in batch processing: {exc}"

    def search_files(self, search_text: str, directory: str = ".", file_pattern: str = "", case_sensitive: bool = False) -> str:
        """Search files by content."""
        try:
            dir_path = Path(directory)
            is_safe, reason = is_path_safe(str(dir_path))
            if not is_safe:
                return f"Security: {reason}"
            
            if not dir_path.exists() or not dir_path.is_dir():
                return f"Error: Directory '{directory}' does not exist or is not a directory"
            
            # Build file list
            if file_pattern:
                file_paths = list(dir_path.rglob(file_pattern))
            else:
                file_paths = list(dir_path.rglob("*"))
            
            # Filter out directories
            file_paths = [fp for fp in file_paths if fp.is_file()]
            
            # Prepare regex
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(search_text, flags)
            
            results = []
            for filepath in file_paths:
                # Check path safety
                is_safe, reason = is_path_safe(str(filepath))
                if not is_safe:
                    continue
                
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    matches = list(pattern.finditer(content))
                    if matches:
                        results.append(f"{filepath}: {len(matches)} matches")
                except Exception:
                    continue  # Skip binary files
            
            if not results:
                return f"No matches found for '{search_text}' in {len(file_paths)} files"
            
            return f"Found {len(results)} files with matches:\n" + "\n".join(results[:20]) + \
                   (f"\n... and {len(results) - 20} more" if len(results) > 20 else "")
        
        except Exception as exc:
            return f"Error in file search: {exc}"

    def compare_files(self, file1: str, file2: str, context_lines: int = 3) -> str:
        """Compare two files and show diff."""
        try:
            # Check path safety
            for fpath in [file1, file2]:
                is_safe, reason = is_path_safe(fpath)
                if not is_safe:
                    return f"Security for {fpath}: {reason}"
            
            # Read files
            try:
                lines1 = Path(file1).read_text(encoding="utf-8").splitlines()
                lines2 = Path(file2).read_text(encoding="utf-8").splitlines()
            except Exception as e:
                return f"Error reading files: {e}"
            
            # Generate diff
            diff = list(difflib.unified_diff(
                lines1, lines2,
                fromfile=file1, tofile=file2,
                lineterm='', n=context_lines
            ))
            
            if not diff:
                return f"Files '{file1}' and '{file2}' are identical"
            
            return f"Differences between '{file1}' and '{file2}':\n" + "\n".join(diff[:50]) + \
                   (f"\n... diff truncated to 50 lines" if len(diff) > 50 else "")
        
        except Exception as exc:
            return f"Error comparing files: {exc}"

    def extract_archive(self, archive_path: str, extract_dir: str = "") -> str:
        """Extract ZIP/RAR/TAR archive."""
        try:
            # Check path safety
            is_safe, reason = is_path_safe(archive_path)
            if not is_safe:
                return f"Security: {reason}"
            
            archive = Path(archive_path)
            if not archive.exists():
                return f"Error: Archive '{archive_path}' does not exist"
            
            # Determine extract directory
            if extract_dir:
                extract_path = Path(extract_dir)
            else:
                extract_path = archive.parent / archive.stem
            
            is_safe_target, reason_target = is_path_safe(str(extract_path))
            if not is_safe_target:
                return f"Security for extract directory: {reason_target}"
            
            extract_path.mkdir(parents=True, exist_ok=True)
            
            # Extract based on extension
            if archive.suffix.lower() in ['.zip']:
                with zipfile.ZipFile(archive, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                extracted = zip_ref.namelist()
            elif archive.suffix.lower() in ['.tar', '.tar.gz', '.tgz', '.tar.bz2']:
                mode = 'r:gz' if archive.suffix.lower() in ['.tar.gz', '.tgz'] else \
                       'r:bz2' if archive.suffix.lower() in ['.tar.bz2'] else 'r'
                with tarfile.open(archive, mode) as tar_ref:
                    tar_ref.extractall(extract_path)
                extracted = tar_ref.getnames()
            else:
                return f"Error: Unsupported archive format '{archive.suffix}'. Use .zip, .tar, .tar.gz, .tgz, .tar.bz2"
            
            return f"Extracted {len(extracted)} files from '{archive_path}' to '{extract_path}'"
        
        except Exception as exc:
            return f"Error extracting archive: {exc}"

    def create_archive(self, source_path: str, archive_path: str, archive_type: str = "zip") -> str:
        """Create archive from files or directory."""
        try:
            # Check path safety for source and archive
            for fpath in [source_path, archive_path]:
                is_safe, reason = is_path_safe(fpath)
                if not is_safe:
                    return f"Security for {fpath}: {reason}"
            
            source = Path(source_path)
            archive = Path(archive_path)
            
            if not source.exists():
                return f"Error: Source '{source_path}' does not exist"
            
            # Create archive
            if archive_type.lower() == "zip":
                with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    if source.is_file():
                        zipf.write(source, source.name)
                    else:
                        for file_path in source.rglob("*"):
                            if file_path.is_file():
                                arcname = file_path.relative_to(source)
                                zipf.write(file_path, arcname)
                return f"Created ZIP archive '{archive_path}' from '{source_path}'"
            
            elif archive_type.lower() == "tar":
                mode = 'w'
                if archive.suffix.lower() in ['.tar.gz', '.tgz']:
                    mode = 'w:gz'
                elif archive.suffix.lower() in ['.tar.bz2']:
                    mode = 'w:bz2'
                
                with tarfile.open(archive, mode) as tarf:
                    if source.is_file():
                        tarf.add(source, source.name)
                    else:
                        tarf.add(source, arcname=source.name)
                return f"Created TAR archive '{archive_path}' from '{source_path}'"
            
            else:
                return f"Error: Unsupported archive type '{archive_type}'. Use 'zip' or 'tar'"
        
        except Exception as exc:
            return f"Error creating archive: {exc}"

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

    def browser_extract_data(self, session_id: str = "default", selectors: Optional[dict] = None, as_table: bool = False) -> str:
        try:
            if selectors is None:
                selectors = {}
            return self._get_browser_manager().extract_data(
                session_id=session_id,
                selectors=selectors,
                as_table=as_table,
            )
        except Exception as exc:
            return f"Browser Error: {exc}"

    def browser_close(self, session_id: str = "default") -> str:
        try:
            return self._get_browser_manager().close(session_id=session_id)
        except Exception as exc:
            return f"Browser Error: {exc}"

    def execute_code(self, language: str, code: str, timeout_seconds: int = 10, args: Optional[list] = None) -> str:
        """Execute code snippet in specified language."""
        try:
            if args is None:
                args = []
            
            # Map language to interpreter
            interpreters = {
                "python": ["python", "-c"],
                "javascript": ["node", "-e"],
                "shell": ["bash", "-c"],
                "bash": ["bash", "-c"],
            }
            
            if language not in interpreters:
                return f"Error: Unsupported language '{language}'. Supported: {list(interpreters.keys())}"
            
            interpreter_cmd = interpreters[language]
            
            # Build command
            cmd = interpreter_cmd + [code] + args
            
            # Security check - prevent dangerous commands
            cmd_str = " ".join(cmd)
            is_safe, reason = is_command_safe(cmd_str)
            if not is_safe:
                return f"Security: Command blocked. {reason}"
            
            # Execute
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(WORKSPACE_ROOT),
            )
            
            output = completed.stdout
            error = completed.stderr
            
            result = f"Exit code: {completed.returncode}\n"
            if output:
                result += f"Output:\n{output[:2000]}"
            if error:
                result += f"\nError:\n{error[:2000]}"
            
            return result
            
        except subprocess.TimeoutExpired:
            return f"Error: Code execution timed out after {timeout_seconds} seconds."
        except FileNotFoundError as exc:
            return f"Error: Interpreter not found for '{language}': {exc}"
        except Exception as exc:
            return f"Error executing code: {exc}"

    def git_status(self, operation: str, path: str = ".", limit: int = 100) -> str:
        """Run git status/diff/log."""
        try:
            # Check path safety
            is_safe, reason = is_path_safe(path)
            if not is_safe:
                return f"Security: {reason}"
            
            repo_path = Path(path)
            if not repo_path.exists():
                return f"Error: Path '{path}' does not exist"
            
            # Build git command
            if operation == "status":
                cmd = ["git", "status", "--short"]
            elif operation == "diff":
                cmd = ["git", "diff", "--no-ext-diff"]
            elif operation == "log":
                cmd = ["git", "log", f"--oneline", f"-{limit}"]
            elif operation == "branch":
                cmd = ["git", "branch", "-a"]
            else:
                return f"Error: Unknown git operation '{operation}'. Use status/diff/log/branch."
            
            # Security check
            cmd_str = " ".join(cmd)
            is_safe, reason = is_command_safe(cmd_str)
            if not is_safe:
                return f"Security: Command blocked. {reason}"
            
            # Execute
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(repo_path),
            )
            
            output = completed.stdout if completed.returncode == 0 else completed.stderr
            
            # Limit output
            if len(output) > 5000:
                output = output[:5000] + "\n...[truncated]"
            
            return f"Git {operation} (exit {completed.returncode}):\n{output}"
            
        except subprocess.TimeoutExpired:
            return f"Error: Git command timed out."
        except Exception as exc:
            return f"Error running git command: {exc}"

    def run_dependency_command(self, tool: str, command: str, package: str = "", path: str = ".") -> str:
        """Run dependency management command."""
        try:
            # Check path safety
            is_safe, reason = is_path_safe(path)
            if not is_safe:
                return f"Security: {reason}"
            
            work_dir = Path(path)
            if not work_dir.exists():
                return f"Error: Path '{path}' does not exist"
            
            # Build command based on tool
            if tool == "pip":
                cmd = ["pip", command]
                if package:
                    cmd.append(package)
            elif tool == "npm":
                cmd = ["npm", command]
                if package:
                    cmd.append(package)
            elif tool == "yarn":
                cmd = ["yarn", command]
                if package:
                    cmd.append(package)
            elif tool == "poetry":
                cmd = ["poetry", command]
                if package:
                    cmd.append(package)
            elif tool == "cargo":
                cmd = ["cargo", command]
                if package:
                    cmd.append(package)
            else:
                return f"Error: Unsupported tool '{tool}'. Supported: pip, npm, yarn, poetry, cargo."
            
            # Security check - ensure install/update commands are safe
            cmd_str = " ".join(cmd)
            is_safe, reason = is_command_safe(cmd_str)
            if not is_safe:
                return f"Security: Command blocked. {reason}"
            
            # Execute
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(work_dir),
            )
            
            output = completed.stdout if completed.returncode == 0 else completed.stderr
            
            # Limit output
            if len(output) > 4000:
                output = output[:4000] + "\n...[truncated]"
            
            return f"{tool} {command} (exit {completed.returncode}):\n{output}"
            
        except subprocess.TimeoutExpired:
            return f"Error: Dependency command timed out."
        except Exception as exc:
            return f"Error running dependency command: {exc}"

    def run_tests(self, framework: str, path: str = ".", args: str = "") -> str:
        """Run test suite."""
        try:
            # Check path safety
            is_safe, reason = is_path_safe(path)
            if not is_safe:
                return f"Security: {reason}"
            
            test_path = Path(path)
            if not test_path.exists():
                return f"Error: Path '{path}' does not exist"
            
            # Build test command
            if framework == "pytest":
                cmd = ["pytest"]
                if args:
                    cmd.extend(args.split())
            elif framework == "unittest":
                cmd = ["python", "-m", "unittest"]
                if args:
                    cmd.extend(args.split())
            elif framework == "jest":
                cmd = ["npx", "jest"]
                if args:
                    cmd.extend(args.split())
            elif framework == "mocha":
                cmd = ["npx", "mocha"]
                if args:
                    cmd.extend(args.split())
            else:
                return f"Error: Unsupported test framework '{framework}'. Supported: pytest, unittest, jest, mocha."
            
            # Security check
            cmd_str = " ".join(cmd)
            is_safe, reason = is_command_safe(cmd_str)
            if not is_safe:
                return f"Security: Command blocked. {reason}"
            
            # Execute
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(test_path),
            )
            
            output = completed.stdout if completed.returncode == 0 else completed.stderr
            
            # Limit output
            if len(output) > 6000:
                output = output[:6000] + "\n...[truncated]"
            
            return f"Test {framework} (exit {completed.returncode}):\n{output}"
            
        except subprocess.TimeoutExpired:
            return f"Error: Test execution timed out."
        except Exception as exc:
            return f"Error running tests: {exc}"

    def system_resource_stats(self) -> str:
        """Get system resource statistics."""
        try:
            import psutil
        except ImportError:
            # Fallback to basic system commands
            try:
                import platform
                system = platform.system().lower()
                if system == "windows":
                    # Use WMIC
                    cpu = subprocess.run(["wmic", "cpu", "get", "loadpercentage"], capture_output=True, text=True).stdout
                    mem = subprocess.run(["wmic", "os", "get", "freephysicalmemory,totalvisiblememorysize"], capture_output=True, text=True).stdout
                    disk = subprocess.run(["wmic", "logicaldisk", "get", "size,freespace"], capture_output=True, text=True).stdout
                    return f"Windows stats:\nCPU:\n{cpu}\nMemory:\n{mem}\nDisk:\n{disk}"
                else:
                    # Linux/Mac
                    cpu = subprocess.run(["top", "-bn1"], capture_output=True, text=True).stdout[:500]
                    mem = subprocess.run(["free", "-h"], capture_output=True, text=True).stdout
                    disk = subprocess.run(["df", "-h"], capture_output=True, text=True).stdout
                    return f"System stats:\nCPU:\n{cpu}\nMemory:\n{mem}\nDisk:\n{disk}"
            except Exception as e:
                return f"Error collecting system stats: {e}"
        
        # psutil is available
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            stats = [
                f"CPU Usage: {cpu_percent}%",
                f"Memory: {memory.percent}% used ({memory.used / (1024**3):.2f} GB / {memory.total / (1024**3):.2f} GB)",
                f"Disk: {disk.percent}% used ({disk.used / (1024**3):.2f} GB / {disk.total / (1024**3):.2f} GB)",
            ]
            return "\n".join(stats)
        except Exception as e:
            return f"Error using psutil: {e}"

    def list_processes(self, filter_str: str = "", limit: int = 50) -> str:
        """List running processes."""
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    if filter_str and filter_str.lower() not in pinfo['name'].lower():
                        continue
                    processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                if len(processes) >= limit * 2:  # collect extra for filtering
                    break
            
            # Sort by CPU desc
            processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
            processes = processes[:limit]
            
            lines = []
            for p in processes:
                lines.append(f"{p['pid']:6} {p['name']:20} CPU:{p.get('cpu_percent', 0):5.1f}% MEM:{p.get('memory_percent', 0):5.1f}%")
            
            if not lines:
                return "No processes found."
            return f"Top {len(lines)} processes:\n" + "\n".join(lines)
            
        except ImportError:
            # Fallback to system command
            system = platform.system().lower()
            if system == "windows":
                cmd = ["tasklist", "/fo", "csv", "/nh"]
            else:
                cmd = ["ps", "aux"]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                output = result.stdout
                if filter_str:
                    lines = output.splitlines()
                    filtered = [line for line in lines if filter_str.lower() in line.lower()]
                    output = "\n".join(filtered[:limit])
                else:
                    # limit lines
                    lines = output.splitlines()
                    output = "\n".join(lines[:limit])
                return f"Process list ({system}):\n{output}"
            except Exception as e:
                return f"Error listing processes: {e}"

    def kill_process(self, pid: int, signal: str = "SIGTERM") -> str:
        """Terminate a process."""
        # Safety: only allow killing processes within the workspace? Not feasible.
        # Instead, we can allow but warn.
        if pid <= 0:
            return "Error: Invalid PID."
        
        # Convert signal to OS-specific signal number
        import signal as sig
        sig_map = {}
        sig_map["SIGTERM"] = getattr(sig, "SIGTERM", 15)
        sig_map["SIGKILL"] = getattr(sig, "SIGKILL", 9)
        if signal not in sig_map:
            return f"Error: Unsupported signal '{signal}'. Use SIGTERM or SIGKILL."
        
        try:
            import os
            os.kill(pid, sig_map[signal])
            return f"Sent {signal} to process {pid}."
        except ProcessLookupError:
            return f"Error: Process {pid} not found."
        except PermissionError:
            return f"Error: Permission denied to kill process {pid}."
        except Exception as e:
            return f"Error killing process: {e}"

    def tail_log(self, filepath: str, lines: int = 50, follow: bool = False) -> str:
        """Tail a log file."""
        # Check path safety
        is_safe, reason = is_path_safe(filepath)
        if not is_safe:
            return f"Security: {reason}"
        
        try:
            path = Path(filepath)
            if not path.exists():
                return f"Error: File '{filepath}' does not exist."
            
            if follow:
                # Following not supported in this simple version
                return "Follow mode not implemented. Use lines parameter."
            
            # Read last N lines efficiently
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # Seek from end
                f.seek(0, 2)
                file_size = f.tell()
                block_size = 4096
                blocks = []
                total_bytes = 0
                while total_bytes < file_size and len(blocks) < lines:
                    if file_size - total_bytes > block_size:
                        f.seek(-(block_size + total_bytes), 2)
                        blocks.append(f.read(block_size))
                    else:
                        f.seek(0)
                        blocks.append(f.read(file_size - total_bytes))
                    total_bytes += len(blocks[-1])
                
                # Concatenate and split lines
                text = ''.join(reversed(blocks))
                lines_list = text.splitlines()[-lines:]
                return f"Last {len(lines_list)} lines of {filepath}:\n" + "\n".join(lines_list)
                
        except Exception as e:
            return f"Error tailing log: {e}"

    def analyze_logs(self, filepath: str, pattern: str, hours: int = 24) -> str:
        """Search logs for patterns."""
        is_safe, reason = is_path_safe(filepath)
        if not is_safe:
            return f"Security: {reason}"
        
        import re
        try:
            path = Path(filepath)
            if not path.exists():
                return f"Error: File '{filepath}' does not exist."
            
            regex = re.compile(pattern)
            matches = []
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        matches.append((line_num, line.strip()))
                        if len(matches) >= 1000:
                            break
            
            if not matches:
                return f"No matches found for pattern '{pattern}' in {filepath}."
            
            # Count matches per hour? Not implemented
            return f"Found {len(matches)} matches for pattern '{pattern}':\n" + \
                   "\n".join([f"Line {ln}: {text[:100]}" for ln, text in matches[:20]]) + \
                   (f"\n... and {len(matches) - 20} more" if len(matches) > 20 else "")
            
        except re.error as e:
            return f"Invalid regex pattern: {e}"
        except Exception as e:
            return f"Error analyzing logs: {e}"

    def create_backup(self, source_path: str, backup_dir: str = "", compression: str = "zip") -> str:
        """Create timestamped backup."""
        is_safe, reason = is_path_safe(source_path)
        if not is_safe:
            return f"Security: {reason}"
        
        if backup_dir:
            is_safe_target, reason_target = is_path_safe(backup_dir)
            if not is_safe_target:
                return f"Security for backup directory: {reason_target}"
        
        try:
            source = Path(source_path)
            if not source.exists():
                return f"Error: Source '{source_path}' does not exist."
            
            # Determine backup directory
            if backup_dir:
                backup_path = Path(backup_dir)
            else:
                backup_path = Path.cwd() / "backups"
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # Generate timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if source.is_file():
                backup_name = f"{source.stem}_{timestamp}.{compression}"
            else:
                backup_name = f"{source.name}_{timestamp}.{compression}"
            
            archive_path = backup_path / backup_name
            
            # Use existing create_archive method
            return self.create_archive(str(source), str(archive_path), "zip" if compression == "zip" else "tar")
            
        except Exception as e:
            return f"Error creating backup: {e}"
