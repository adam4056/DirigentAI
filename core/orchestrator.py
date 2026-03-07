import os
import json
import logging
from datetime import datetime
from typing import Callable, Optional, Dict, List
from core.llm.factory import LLMFactory
from core.config import DirigentConfig
from agents.worker import Worker

logger = logging.getLogger("dirigent.orchestrator")


class Orchestrator:
    """The CEO/Orchestrator of the DirigentAI digital firm."""

    MAX_HISTORY_TURNS = 20
    MAX_FUNCTION_CALL_ITERATIONS = 10

    def __init__(self, config_file: Optional[str] = None):
        self.config = DirigentConfig(config_file)
        orchestrator_config = self.config.get_orchestrator_config()

        api_key = orchestrator_config.get("api_key")
        model = orchestrator_config.get("model", "unknown")
        if not api_key:
            api_key_env = orchestrator_config.get("api_key_env", "API_KEY")
            raise ValueError(
                f"API key not found for approved model '{model}'. "
                f"Set environment variable {api_key_env} or update config/dirigent.yaml."
            )

        self.llm_client = LLMFactory.create_client_from_config(orchestrator_config)
        self.model_name = orchestrator_config.get("model", "gemini-1.5-flash")
        self.memory_file = "memory/MEMORY.md"
        self.soul_file = "SOUL.md"
        self.db_file = "memory/workers.json"
        self.tasks_file = "memory/tasks.json"
        self.sessions_file = "memory/sessions.json"

        self.workers: dict[str, Worker] = {}
        self.next_worker_id: int = 1

        workers_config = self.config.get_workers_config()
        ui_config = self.config.get_ui_config()
        self.max_workers: int = workers_config.get("max_workers", 15)
        self.on_schedule_callback: Optional[Callable[[dict], None]] = None
        hide_env = os.getenv("HIDE_WORKER_CREATION")
        self.hide_worker_creation = hide_env.lower() == "true" if hide_env is not None else ui_config.get("hide_worker_creation", True)
        self.sessions: dict[str, list] = {}

        self.load_memory()
        self.load_soul()
        self.load_sessions()
        self.load_workers_db()

        self.tools = [
            {
                "name": "hire_specialist",
                "description": "Creates a permanent specialist (employee) to be stored in the DB for future use.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of capabilities (e.g., 'terminal', 'file_ops', 'web_ops').",
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of this worker's specialization.",
                        },
                    },
                    "required": ["capabilities", "description"],
                },
            },
            {
                "name": "spawn_temporary_worker",
                "description": "Creates a temporary worker (contractor) for a one-time task. Will not be saved to DB.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of capabilities.",
                        }
                    },
                    "required": ["capabilities"],
                },
            },
            {
                "name": "delegate_task",
                "description": "Delegates a specific task to an existing worker.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "worker_id": {
                            "type": "string",
                            "description": "The ID of the worker to delegate to (e.g., 'worker_1').",
                        },
                        "task": {
                            "type": "string",
                            "description": "Human-like description of the task for the worker.",
                        },
                    },
                    "required": ["worker_id", "task"],
                },
            },
            {
                "name": "schedule_routine",
                "description": "Schedules a recurring routine (e.g., at 1 AM) or a one-time task in the future.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_description": {
                            "type": "string",
                            "description": "What needs to be done (e.g., 'Check emails and send summary').",
                        },
                        "schedule_type": {
                            "type": "string",
                            "enum": ["cron", "interval", "date"],
                            "description": "Type of scheduling.",
                        },
                        "schedule_value": {
                            "type": "string",
                            "description": "Scheduler value (e.g., '0 1 * * *' for 1:00 AM, or '3600' for seconds).",
                        },
                    },
                    "required": ["task_description", "schedule_type", "schedule_value"],
                },
            },
            {
                "name": "update_memory",
                "description": "Saves important information into long-term strategic memory (MEMORY.md).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The information to be saved.",
                        }
                    },
                    "required": ["content"],
                },
            },
        ]

    def load_sessions(self):
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    self.sessions = json.load(f)
            except Exception as e:
                logger.error(f"Error loading sessions: {e}")
                self.sessions = {}
        else:
            self.sessions = {}

    def save_sessions(self):
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)
        with open(self.sessions_file, "w", encoding="utf-8") as f:
            json.dump(self.sessions, f, indent=2, ensure_ascii=False)

    def get_or_create_session(self, session_id: str = "default") -> List[Dict[str, str]]:
        if session_id not in self.sessions:
            self.sessions[session_id] = []
            self.save_sessions()
            logger.debug(f"Created new session: {session_id}")
        return self.sessions[session_id]

    def trim_session_history(self, session_id: str = "default") -> None:
        if session_id in self.sessions:
            history = self.sessions[session_id]
            max_items = self.MAX_HISTORY_TURNS * 2
            if len(history) > max_items:
                self.sessions[session_id] = history[-max_items:]
                self.save_sessions()
                logger.debug(f"Trimmed session {session_id}: {len(history)} -> {max_items} items")

    def clear_session(self, session_id: str = "default") -> None:
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save_sessions()
            logger.info(f"Session cleared: {session_id}")

    def list_sessions(self) -> list[str]:
        return list(self.sessions.keys())

    def load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.memory = f.read()
        else:
            self.memory = ""

    def save_memory(self):
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            f.write(self.memory)

    def load_soul(self):
        if os.path.exists(self.soul_file):
            with open(self.soul_file, "r", encoding="utf-8") as f:
                self.soul = f.read()
        else:
            self.soul = "I am DirigentAI, the orchestrator and CEO of this digital firm."

    def _normalize_worker_model(self, model: Optional[str]) -> str:
        return self.config.resolve_model(model)

    def load_workers_db(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for w_data in data:
                    normalized_data = dict(w_data)
                    normalized_data["model"] = self._normalize_worker_model(w_data.get("model"))
                    worker = Worker.from_dict(normalized_data, api_key=None)
                    self.workers[worker.worker_id] = worker
                    try:
                        num = int(worker.worker_id.split("_")[1])
                        if num >= self.next_worker_id:
                            self.next_worker_id = num + 1
                    except (ValueError, IndexError):
                        pass
                logger.info(f"Loaded {len(self.workers)} specialists from DB.")
            except Exception as e:
                logger.error(f"Error loading workers DB: {e}")

    def save_workers_db(self):
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        specialists = [w.to_dict() for w in self.workers.values() if w.description]
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(specialists, f, indent=4, ensure_ascii=False)

    def _match_preset(self, capabilities: list[str]) -> Optional[dict]:
        worker_config = self.config.get_workers_config()
        presets = worker_config.get("presets", {})
        for preset_config in presets.values():
            if sorted(capabilities) == sorted(preset_config.get("capabilities", [])):
                return preset_config
        return None

    def _get_worker_model(self, capabilities: list[str]) -> str:
        preset = self._match_preset(capabilities)
        if preset:
            task_type = preset.get("task_type")
            if task_type:
                task_model = self.config.get_model_for_task(task_type)
                if task_model:
                    return task_model
            return self._normalize_worker_model(preset.get("model"))

        workers_config = self.config.get_workers_config()
        return self._normalize_worker_model(workers_config.get("default_model"))

    def add_worker(self, capabilities: list[str] | None = None, description: str = ""):
        if len(self.workers) >= self.max_workers:
            return None, f"Maximum number of workers reached ({self.max_workers})."
        worker_id = f"worker_{self.next_worker_id}"
        self.next_worker_id += 1
        default_capabilities = capabilities or ["terminal", "file_ops"]
        model = self._get_worker_model(default_capabilities)
        worker = Worker(worker_id, default_capabilities, description, api_key=None, model=model)
        self.workers[worker_id] = worker

        if description:
            self.save_workers_db()
            logger.info(f"Hired permanent specialist {worker_id}: {description}")
            return worker_id, f"Hired permanent specialist {worker_id}: {description}"

        logger.info(f"Spawned temporary worker {worker_id}: {capabilities}")
        return worker_id, f"Created temporary worker {worker_id} with capabilities {capabilities}"

    def process(self, user_input: str, is_routine: bool = False, session_id: str = "default") -> str:
        if not is_routine:
            logger.info(f"[User@{session_id}]: {user_input}")
        else:
            logger.info(f"[ROUTINE]: Running scheduled task: {user_input}")

        specialists_list = "\n".join(
            [f"- {w.worker_id}: {w.description} (Capabilities: {w.capabilities}, Model: {w.model})" for w in self.workers.values() if w.description]
        )
        approved_models = ", ".join(self.config.get_approved_models()) or "none"
        active_models = ", ".join(self.config.get_available_models()) or self.model_name
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_instruction = f"""
### SYSTEM OPERATIONAL MANUAL (INTERNAL)
You are the orchestrator of the DirigentAI firm.

CURRENT TIME: {now}

INTERNAL PERSONALITY & ETHICS (SOUL):
{self.soul}

STRATEGIC NOTEPAD (MEMORY):
{self.memory}

MODEL POLICY:
- Approved models: {approved_models}
- Models currently usable with configured API keys: {active_models}
- Never request or imply use of any model outside this policy.

FIRM STATUS:
- Permanent specialists in DB: {specialists_list if specialists_list else 'None hired yet.'}
- Currently active workers in RAM: {list(self.workers.keys())}

SPECIALIST RECIPES:
- For coding or repo work, prefer capabilities ["terminal", "file_ops"].
- For web research, current news, release dates, dynamic websites, or login flows, prefer capabilities ["web_ops", "browser_ops", "file_ops"].
- For local analysis only, prefer capabilities ["file_ops"].

YOUR TECHNICAL DUTIES:
1. Analysis: Decide if the request requires a technical action.
2. Delegation: For any technical query (files, processes, system) you MUST invoke a tool call.
3. Web and current-events work: If the user asks for web research, current news, release dates, or external facts, you should create or use a worker with web_ops and browser_ops when available.
4. Validation: Never hallucinate results. Respond to the user ONLY when you have data from a worker in context, unless the user is explicitly asking for a limitation explanation.
5. Hiring: If you need a new skill, hire a specialist (permanent) or spawn a contractor (temporary).
6. Memory: Use update_memory only for facts defining the relationship with the user or project parameters.
7. Context: You have access to previous conversation history in this session. Use it to maintain coherent multi-turn conversations.

Language: Always communicate in English.
"""

        session_history = self.get_or_create_session(session_id)
        session_history.append({"role": "user", "content": user_input})
        self.save_sessions()
        current_messages = list(session_history)
        iterations = 0

        while iterations < self.MAX_FUNCTION_CALL_ITERATIONS:
            iterations += 1
            try:
                response = self.llm_client.generate_content(
                    system_instruction=system_instruction,
                    messages=current_messages,
                    tools=self.tools,
                    tool_choice="auto" if self.tools else "none",
                )
            except Exception as e:
                error_msg = f"AI model error: {e}"
                logger.error(error_msg)
                return error_msg

            response_text = response.get("text", "")
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                if response_text:
                    session_history.append({"role": "assistant", "content": response_text})
                    self.save_sessions()
                self.trim_session_history(session_id)
                if response_text:
                    logger.info(f"[DirigentAI@{session_id}]: {response_text[:100]}...")
                return response_text or "I couldn't generate a response."

            assistant_tool_calls = []
            tool_results = []
            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id") or f"call_{tool_call.get('name', 'tool')}"
                fn_name = tool_call.get("name")
                args = tool_call.get("args", {})
                logger.info(f"[Function Call]: {fn_name}({args})")
                result = self._execute_function(fn_name, args)
                assistant_tool_calls.append({"id": tool_call_id, "name": fn_name, "args": args})
                tool_results.append({"tool_call_id": tool_call_id, "name": fn_name, "result": result})

            current_messages.append({
                "role": "assistant",
                "content": response_text,
                "tool_calls": assistant_tool_calls,
            })
            for tool_result in tool_results:
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result["tool_call_id"],
                    "name": tool_result["name"],
                    "content": str(tool_result["result"]),
                })

        logger.warning(f"Hit max function call iterations ({self.MAX_FUNCTION_CALL_ITERATIONS}) for session {session_id}")
        for msg in reversed(current_messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                session_history.append(msg)
                self.save_sessions()
                break
        self.trim_session_history(session_id)
        return "I reached the maximum number of tool calls for this request. Here is what I have so far."

    def _execute_function(self, fn_name: str, args: dict) -> str:
        try:
            if fn_name == "hire_specialist":
                worker_id, result = self.add_worker(args.get("capabilities"), args.get("description", ""))
                if self.hide_worker_creation:
                    result = "Specialist ready."
            elif fn_name == "spawn_temporary_worker":
                worker_id, result = self.add_worker(args.get("capabilities"))
                if self.hide_worker_creation:
                    result = "Worker ready."
            elif fn_name == "delegate_task":
                w_id = args.get("worker_id", "")
                worker = self.workers.get(w_id)
                result = worker.execute(args.get("task", "")) if worker else f"Error: Worker '{w_id}' does not exist."
            elif fn_name == "schedule_routine":
                task_data = {
                    "task_description": args.get("task_description"),
                    "schedule_type": args.get("schedule_type"),
                    "schedule_value": args.get("schedule_value"),
                }
                if self.on_schedule_callback:
                    self.on_schedule_callback(task_data)
                result = f"Task '{task_data['task_description']}' scheduled ({task_data['schedule_type']}: {task_data['schedule_value']})."
            elif fn_name == "update_memory":
                self.memory += f"\n- {args.get('content')}"
                self.save_memory()
                result = "Memory updated."
            else:
                result = f"Error: Unknown function '{fn_name}'."
        except Exception as e:
            result = f"Error executing {fn_name}: {e}"
            logger.error(result)
        return result
