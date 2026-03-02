import os
import json
import logging
from datetime import datetime
from typing import Callable, Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agents.worker import Worker

load_dotenv()

logger = logging.getLogger("dirigent.orchestrator")


class Orchestrator:
    """
    The CEO/Orchestrator of the DirigentAI digital firm.
    Manages workers, delegates tasks, and maintains conversation context.
    """

    MAX_HISTORY_TURNS = 20  # Max conversation turns kept in session context
    MAX_FUNCTION_CALL_ITERATIONS = 10  # Prevent infinite function-calling loops

    def __init__(self, model_name: str = "gemini-3-flash-preview"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env file")

        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.memory_file = "memory/MEMORY.md"
        self.soul_file = "SOUL.md"
        self.db_file = "memory/workers.json"
        self.tasks_file = "memory/tasks.json"

        self.workers: dict[str, Worker] = {}  # worker_id -> Worker instance
        self.next_worker_id: int = 1
        self.max_workers: int = 15
        self.on_schedule_callback: Optional[Callable[[dict], None]] = None

        # Session conversation history per client (session_id -> list of Content)
        self.sessions: dict[str, list] = {}

        self.load_memory()
        self.load_soul()
        self.load_workers_db()

        # Define tools for function calling
        self.tools = [
            types.Tool(
                function_declarations=[
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
                            "required": [
                                "task_description",
                                "schedule_type",
                                "schedule_value",
                            ],
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
            )
        ]

    # ── Session context management ──────────────────────────────────────

    def get_or_create_session(self, session_id: str = "default") -> list:
        """Get or create a conversation session by ID."""
        if session_id not in self.sessions:
            self.sessions[session_id] = []
            logger.debug(f"Created new session: {session_id}")
        return self.sessions[session_id]

    def trim_session_history(self, session_id: str = "default") -> None:
        """Trim session history to keep only the last MAX_HISTORY_TURNS exchanges."""
        if session_id in self.sessions:
            history = self.sessions[session_id]
            # Each "turn" is roughly a user message + model response (2 Content objects)
            # We also count function call/response pairs. Keep the last N items.
            max_items = self.MAX_HISTORY_TURNS * 2
            if len(history) > max_items:
                self.sessions[session_id] = history[-max_items:]
                logger.debug(
                    f"Trimmed session {session_id}: {len(history)} -> {max_items} items"
                )

    def clear_session(self, session_id: str = "default") -> None:
        """Clear a specific session's conversation history."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Session cleared: {session_id}")

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        return list(self.sessions.keys())

    # ── Persistence ──────────────────────────────────────────────────────

    def load_memory(self):
        """Load strategic memory from MEMORY.md."""
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.memory = f.read()
        else:
            self.memory = ""

    def save_memory(self):
        """Save strategic memory to MEMORY.md."""
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            f.write(self.memory)

    def load_soul(self):
        """Load AI personality definition from SOUL.md."""
        if os.path.exists(self.soul_file):
            with open(self.soul_file, "r", encoding="utf-8") as f:
                self.soul = f.read()
        else:
            self.soul = "I am DirigentAI, the orchestrator and CEO of this digital firm."

    def load_workers_db(self):
        """Load persistent specialist workers from JSON database."""
        if os.path.exists(self.db_file):
            try:
                api_key = os.getenv("GEMINI_API_KEY")
                with open(self.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for w_data in data:
                        worker = Worker.from_dict(w_data, api_key=api_key)
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
        """Save specialist workers to JSON database."""
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        specialists = [w.to_dict() for w in self.workers.values() if w.description]
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(specialists, f, indent=4, ensure_ascii=False)

    # ── Worker management ────────────────────────────────────────────────

    def add_worker(self, capabilities: list[str] | None = None, description: str = ""):
        """Add a new worker (permanent specialist or temporary contractor)."""
        if len(self.workers) >= self.max_workers:
            return None, f"Maximum number of workers reached ({self.max_workers})."
        worker_id = f"worker_{self.next_worker_id}"
        self.next_worker_id += 1
        api_key = os.getenv("GEMINI_API_KEY")
        worker = Worker(worker_id, capabilities, description, api_key=api_key)
        self.workers[worker_id] = worker

        if description:
            self.save_workers_db()
            logger.info(f"Hired permanent specialist {worker_id}: {description}")
            return worker_id, f"Hired permanent specialist {worker_id}: {description}"
        else:
            logger.info(f"Spawned temporary worker {worker_id}: {capabilities}")
            return (
                worker_id,
                f"Created temporary worker {worker_id} with capabilities {capabilities}",
            )

    # ── Main processing loop ───────────────────────────────────────────

    def process(
        self, user_input: str, is_routine: bool = False, session_id: str = "default"
    ) -> str:
        """
        Process a user message with full session context.

        Args:
            user_input: The user's message text.
            is_routine: Whether this is an automated/scheduled task.
            session_id: Unique session identifier for conversation continuity.

        Returns:
            The AI's response text.
        """
        if not is_routine:
            logger.info(f"[User@{session_id}]: {user_input}")
        else:
            logger.info(f"[ROUTINE]: Running scheduled task: {user_input}")

        # Build dynamic system instruction with current state
        specialists_list = "\n".join(
            [
                f"- {w.worker_id}: {w.description} (Capabilities: {w.capabilities})"
                for w in self.workers.values()
                if w.description
            ]
        )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_instruction = f"""
### SYSTEM OPERATIONAL MANUAL (INTERNAL)
You are the orchestrator connected to the Gemini API. Your technical role is to lead the DirigentAI firm.

CURRENT TIME: {now}

INTERNAL PERSONALITY & ETHICS (SOUL):
{self.soul}

STRATEGIC NOTEPAD (MEMORY):
{self.memory}

FIRM STATUS:
- Permanent specialists in DB: {specialists_list if specialists_list else "None hired yet."}
- Currently active workers in RAM: {list(self.workers.keys())}

YOUR TECHNICAL DUTIES:
1. Analysis: Decide if the request requires a technical action.
2. Delegation: For any technical query (files, processes, system) you MUST invoke a tool call.
3. Validation: Never hallucinate results. Respond to the user ONLY when you have data from a worker in context.
4. Hiring: If you need a new skill, hire a specialist (permanent) or spawn a contractor (temporary).
5. Memory: Use update_memory only for facts defining the relationship with the user or project parameters.
6. Context: You have access to previous conversation history in this session. Use it to maintain coherent multi-turn conversations.

Language: Always communicate in English.
"""

        # Get session history and append the new user message
        session_history = self.get_or_create_session(session_id)
        new_user_content = types.Content(
            role="user", parts=[types.Part(text=user_input)]
        )
        session_history.append(new_user_content)

        # Build contents: full session history for context
        contents = list(session_history)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=self.tools,
            automatic_function_calling=types.Automatic_function_calling_config(
                disable=True
            ),
        )

        iterations = 0
        while iterations < self.MAX_FUNCTION_CALL_ITERATIONS:
            iterations += 1

            try:
                response = self.client.models.generate_content(
                    model=self.model_name, contents=contents, config=config
                )
            except Exception as e:
                error_msg = f"AI model error: {e}"
                logger.error(error_msg)
                return error_msg

            model_content = response.candidates[0].content
            contents.append(model_content)
            function_calls = [
                p.function_call for p in model_content.parts if p.function_call
            ]

            if not function_calls:
                # Final text response - save model response to session history
                session_history.append(model_content)
                self.trim_session_history(session_id)
                if response.text:
                    logger.info(f"[DirigentAI@{session_id}]: {response.text[:100]}...")
                return response.text

            for fn_call in function_calls:
                fn_name = fn_call.name
                args = fn_call.args
                logger.info(f"[Function Call]: {fn_name}({args})")

                result = self._execute_function(fn_name, args)

                function_response = types.Part.from_function_response(
                    name=fn_name, response={"result": result}
                )
                contents.append(
                    types.Content(role="user", parts=[function_response])
                )

        # If we hit max iterations, save what we have and return a warning
        logger.warning(
            f"Hit max function call iterations ({self.MAX_FUNCTION_CALL_ITERATIONS}) "
            f"for session {session_id}"
        )
        session_history.append(contents[-1])  # Save last model response
        self.trim_session_history(session_id)
        return "I reached the maximum number of tool calls for this request. Here is what I have so far."

    def _execute_function(self, fn_name: str, args: dict) -> str:
        """Execute a function call from the AI model and return the result."""
        try:
            if fn_name == "hire_specialist":
                worker_id, result = self.add_worker(
                    args.get("capabilities"), args.get("description", "")
                )
            elif fn_name == "spawn_temporary_worker":
                worker_id, result = self.add_worker(args.get("capabilities"))
            elif fn_name == "delegate_task":
                w_id = args.get("worker_id", "")
                worker = self.workers.get(w_id)
                result = (
                    worker.execute(args.get("task", ""))
                    if worker
                    else f"Error: Worker '{w_id}' does not exist."
                )
            elif fn_name == "schedule_routine":
                task_data = {
                    "task_description": args.get("task_description"),
                    "schedule_type": args.get("schedule_type"),
                    "schedule_value": args.get("schedule_value"),
                }
                if self.on_schedule_callback:
                    self.on_schedule_callback(task_data)
                result = (
                    f"Task '{task_data['task_description']}' scheduled "
                    f"({task_data['schedule_type']}: {task_data['schedule_value']})."
                )
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
