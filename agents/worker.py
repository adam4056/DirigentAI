import subprocess
import os
import logging
import requests
from pathlib import Path
from google import genai
from google.genai import types

logger = logging.getLogger("dirigent.worker")

# ── Security Configuration ───────────────────────────────────────────────

# Allowed workspace root for file operations (resolved at import time)
WORKSPACE_ROOT = Path(os.getcwd()).resolve()

# Dangerous commands that workers are NOT allowed to execute
COMMAND_BLACKLIST = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",        # fork bomb
    "format c:",
    "del /f /s /q c:",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init 0",
    "init 6",
    ">()" ,               # partial fork bomb patterns
    "wget",               # prevent drive-by downloads
    "curl -o",
    "curl -O",
    "chmod 777",
    "chmod -R 777",
    "reg delete",
    "reg add",
    "net user",
    "net localgroup",
    "taskkill /f /im",
]

# Patterns in commands to block (partial match)
COMMAND_BLACKLIST_PATTERNS = [
    "rm -rf /",
    "format c:",
    "del /f /s /q c:",
    "> /dev/sd",
    "mkfs.",
    "dd if=/dev",
]


def is_command_safe(command: str) -> tuple[bool, str]:
    """
    Check if a terminal command is safe to execute.
    Returns (is_safe, reason).
    """
    cmd_lower = command.lower().strip()

    # Check exact blacklist
    for blocked in COMMAND_BLACKLIST:
        if blocked.lower() in cmd_lower:
            return False, f"Blocked command pattern: '{blocked}'"

    # Check pattern blacklist
    for pattern in COMMAND_BLACKLIST_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"Blocked dangerous pattern: '{pattern}'"

    return True, "OK"


def is_path_safe(filepath: str) -> tuple[bool, str]:
    """
    Validate that a file path is within the allowed workspace.
    Prevents directory traversal and access to system files.
    Returns (is_safe, reason).
    """
    try:
        # Resolve the path to catch ../ traversal attempts
        resolved = Path(filepath).resolve()

        # Must be within workspace root
        if not str(resolved).startswith(str(WORKSPACE_ROOT)):
            return False, (
                f"Path '{filepath}' resolves to '{resolved}' which is outside "
                f"the allowed workspace '{WORKSPACE_ROOT}'"
            )

        # Block obvious sensitive files/directories
        sensitive_patterns = [
            ".env", ".git/config", ".ssh", "id_rsa", "id_ed25519",
            "credentials", "shadow", "passwd", "authorized_keys",
        ]
        resolved_lower = str(resolved).lower()
        for pattern in sensitive_patterns:
            # Only block exact .env, not files like "my.environment.txt"
            if pattern == ".env" and resolved.name == ".env":
                return False, f"Access to sensitive file '{pattern}' is forbidden."
            elif pattern != ".env" and pattern in resolved_lower:
                return False, f"Access to sensitive path pattern '{pattern}' is forbidden."

        return True, "OK"
    except Exception as e:
        return False, f"Path validation error: {e}"


class Worker:
    """
    An AI-powered worker agent with capability-gated tools.
    Each worker has its own Gemini brain and operates within its permissions.
    """

    MAX_FUNCTION_CALL_ITERATIONS = 8  # Prevent infinite tool loops

    def __init__(
        self,
        worker_id: str,
        capabilities: list[str] | None = None,
        description: str = "",
        api_key: str | None = None,
        model_name: str = "gemini-3-flash-preview",
    ):
        self.worker_id = worker_id
        self.capabilities = capabilities or ["terminal", "file_ops"]
        self.description = description
        self.api_key = api_key
        self.model_name = model_name

        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None

    def to_dict(self) -> dict:
        """Serialize worker to dict for JSON persistence."""
        return {
            "worker_id": self.worker_id,
            "capabilities": self.capabilities,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict, api_key: str | None = None) -> "Worker":
        """Deserialize worker from dict."""
        return cls(
            worker_id=data["worker_id"],
            capabilities=data["capabilities"],
            description=data.get("description", ""),
            api_key=api_key,
        )

    def execute(self, instruction: str) -> str:
        """
        Worker uses AI to understand instructions and select the right tool.
        Implements a function-calling loop with iteration limits.
        """
        if not self.client:
            return f"Worker {self.worker_id}: AI brain missing (API key)."

        logger.info(f"[{self.worker_id}] Thinking: {instruction[:80]}...")

        # Build tool definitions based on capabilities
        worker_tools = self._build_tool_definitions()

        system_prompt = f"""
You are specialized worker {self.worker_id}. Your description: {self.description}.
Your capabilities (permissions): {self.capabilities}.
Available tools: {[t['name'] for t in worker_tools] if worker_tools else 'none'}.

Your boss (DirigentAI) assigned you a task: "{instruction}"

If you lack a tool to complete the task, notify your boss.
Always work within your permissions. Keep output concise and technical.
Language: English.
"""

        contents = [types.Content(role="user", parts=[types.Part(text=instruction)])]

        try:
            iterations = 0
            while iterations < self.MAX_FUNCTION_CALL_ITERATIONS:
                iterations += 1

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=(
                            [types.Tool(function_declarations=worker_tools)]
                            if worker_tools
                            else []
                        ),
                        automatic_function_calling=types.Automatic_function_calling_config(
                            disable=True
                        ),
                    ),
                )

                model_content = response.candidates[0].content
                contents.append(model_content)
                function_calls = [
                    p.function_call for p in model_content.parts if p.function_call
                ]

                if not function_calls:
                    return response.text

                for fn_call in function_calls:
                    fn_name = fn_call.name
                    args = fn_call.args
                    logger.debug(f"[{self.worker_id}] Tool call: {fn_name}({args})")

                    result = self._dispatch_tool(fn_name, args)

                    function_response = types.Part.from_function_response(
                        name=fn_name, response={"result": result}
                    )
                    contents.append(
                        types.Content(role="user", parts=[function_response])
                    )

            logger.warning(
                f"[{self.worker_id}] Hit max iterations ({self.MAX_FUNCTION_CALL_ITERATIONS})"
            )
            return f"Worker {self.worker_id}: Reached maximum tool call limit."

        except Exception as e:
            logger.error(f"[{self.worker_id}] Error: {e}")
            return f"Worker {self.worker_id} Error: {e}"

    def _build_tool_definitions(self) -> list[dict]:
        """Build function declarations based on worker capabilities."""
        worker_tools = []

        if "terminal" in self.capabilities:
            worker_tools.append(
                {
                    "name": "run_terminal_command",
                    "description": "Runs a command in the system shell. Some dangerous commands are blocked for safety.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The command to run.",
                            }
                        },
                        "required": ["command"],
                    },
                }
            )

        if "file_ops" in self.capabilities:
            worker_tools.append(
                {
                    "name": "write_to_file",
                    "description": "Writes text to a file within the workspace directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["filename", "content"],
                    },
                }
            )
            worker_tools.append(
                {
                    "name": "read_file",
                    "description": "Reads file content from within the workspace directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {"filename": {"type": "string"}},
                        "required": ["filename"],
                    },
                }
            )
            worker_tools.append(
                {
                    "name": "list_directory",
                    "description": "Lists files in a directory within the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path (default '.')",
                            }
                        },
                    },
                }
            )

        if "web_ops" in self.capabilities:
            worker_tools.append(
                {
                    "name": "fetch_url",
                    "description": "Downloads text content from a given URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                }
            )

        return worker_tools

    def _dispatch_tool(self, fn_name: str, args: dict) -> str:
        """Route a function call to the appropriate tool method."""
        if fn_name == "run_terminal_command":
            return self.run_terminal(args.get("command", ""))
        elif fn_name == "write_to_file":
            return self.do_write_file(
                args.get("filename", ""), args.get("content", "")
            )
        elif fn_name == "read_file":
            return self.do_read_file(args.get("filename", ""))
        elif fn_name == "list_directory":
            return self.do_list_directory(args.get("path", "."))
        elif fn_name == "fetch_url":
            return self.do_web_fetch(args.get("url", ""))
        else:
            return f"Error: Unknown tool '{fn_name}'."

    # ── Tool implementations ─────────────────────────────────────────────

    def run_terminal(self, command: str) -> str:
        """Execute a shell command with safety checks and timeout."""
        # Security: check command against blacklist
        is_safe, reason = is_command_safe(command)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked command: {command} ({reason})")
            return f"Security: Command blocked. {reason}"

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=15
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            return f"Command '{command}' (exit {result.returncode}):\n{output}"
        except subprocess.TimeoutExpired:
            return f"Error: Command '{command}' timed out after 15 seconds."
        except Exception as e:
            return f"Error: {e}"

    def do_write_file(self, filename: str, content: str) -> str:
        """Write content to a file with path validation."""
        is_safe, reason = is_path_safe(filename)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked file write: {filename} ({reason})")
            return f"Security: {reason}"

        try:
            filepath = Path(filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            return f"OK: {filename} written ({len(content)} chars)."
        except Exception as e:
            return f"Error writing file: {e}"

    def do_read_file(self, filename: str) -> str:
        """Read content from a file with path validation."""
        is_safe, reason = is_path_safe(filename)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked file read: {filename} ({reason})")
            return f"Security: {reason}"

        try:
            return Path(filename).read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

    def do_list_directory(self, path: str = ".") -> str:
        """List directory contents with path validation."""
        is_safe, reason = is_path_safe(path)
        if not is_safe:
            logger.warning(f"[{self.worker_id}] Blocked dir list: {path} ({reason})")
            return f"Security: {reason}"

        try:
            return str(os.listdir(path))
        except Exception as e:
            return f"Error listing directory: {e}"

    def do_web_fetch(self, url: str) -> str:
        """Fetch URL content with size limit."""
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return r.text[:2000]  # Context limit
        except requests.RequestException as e:
            return f"Web Error: {e}"
