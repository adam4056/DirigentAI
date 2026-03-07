import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from core.orchestrator import Orchestrator
from core.interaction_log import log_interaction
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dirigent.engine")


class DirigentEngine:
    """
    Core TCP server engine that bridges clients to the Orchestrator.
    Manages scheduling, client connections, and session routing.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8888):
        self.host = host
        self.port = port
        logger.info("Initializing DirigentEngine...")

        try:
            self.orchestrator = Orchestrator()
        except Exception as e:
            logger.critical(f"Startup error: {e}")
            sys.exit(1)

        self.clients: set = set()
        self.scheduler = AsyncIOScheduler()
        self.tasks_file = "memory/tasks.json"

        self.scheduled_tasks: list[dict] = []
        self.load_tasks()

    def load_tasks(self):
        """Load persisted scheduled tasks from disk."""
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, "r", encoding="utf-8") as f:
                    self.scheduled_tasks = json.load(f)
            except Exception as e:
                logger.error(f"Error loading tasks: {e}")

    def save_tasks(self):
        """Persist scheduled tasks to disk."""
        os.makedirs(os.path.dirname(self.tasks_file), exist_ok=True)
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump(self.scheduled_tasks, f, indent=4, ensure_ascii=False)

    def add_to_scheduler(self, task_data: dict) -> bool:
        """Add a task to the APScheduler. Returns True on success."""
        desc = task_data["task_description"]
        stype = task_data["schedule_type"]
        sval = task_data["schedule_value"]

        try:
            trigger = None
            if stype == "cron":
                trigger = CronTrigger.from_crontab(sval)
            elif stype == "interval":
                trigger = IntervalTrigger(seconds=int(sval))
            elif stype == "date":
                trigger = DateTrigger(run_date=sval)

            if trigger:
                self.scheduler.add_job(
                    self.run_routine_task,
                    trigger,
                    args=[desc],
                    id=f"job_{hash(desc)}",
                    replace_existing=True,
                )
                logger.info(f"Scheduled: {desc}")
                return True
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        return False

    def _handle_command(self, user_input: str, session_id: str) -> str | None:
        """
        Handle built-in slash commands without spending AI tokens.
        Returns response string if handled, None if it should go to AI.
        """
        cmd = user_input.lower().strip()

        if cmd in {"/clear", "/reset"}:
            self.orchestrator.clear_session(session_id)
            return "Session cleared. Starting fresh conversation."

        if cmd == "/workers":
            workers = [
                w for w in self.orchestrator.workers.values() if w.description
            ]
            if not workers:
                return "No permanent specialists hired yet."
            lines = ["Active specialists:"]
            for w in workers:
                lines.append(f"  {w.worker_id}: {w.description} [{', '.join(w.capabilities)}]")
            return "\n".join(lines)

        if cmd == "/status":
            from pathlib import Path
            specialists = [w for w in self.orchestrator.workers.values() if w.description]
            temp_workers = [w for w in self.orchestrator.workers.values() if not w.description]
            session_len = len(self.orchestrator.sessions.get(session_id, []))
            log_size = ""
            log_path = Path("memory/interactions.jsonl")
            if log_path.exists():
                lines = sum(1 for _ in log_path.open(encoding="utf-8"))
                log_size = f"\n  Interaction log: {lines} entries"
            return (
                f"DirigentAI Status\n"
                f"  Specialists (permanent): {len(specialists)}\n"
                f"  Temp workers (RAM): {len(temp_workers)}\n"
                f"  Scheduled tasks: {len(self.scheduled_tasks)}\n"
                f"  Session turns: {session_len // 2}"
                f"{log_size}"
            )

        if cmd == "/help":
            return (
                "Available commands:\n"
                "  /clear    - Reset this session's conversation history\n"
                "  /reset    - Same as /clear\n"
                "  /workers  - List all hired specialist workers\n"
                "  /status   - Show firm status (workers, tasks, session)\n"
                "  /help     - Show this help\n"
                "  exit      - Disconnect"
            )

        return None  # Not a command, pass to AI

    async def run_routine_task(self, task_description: str):
        """Execute a scheduled/routine task through the Orchestrator."""
        logger.info(f"Running routine: {task_description}")
        await asyncio.to_thread(
            self.orchestrator.process,
            task_description,
            is_routine=True,
            session_id="scheduler",
        )

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single client TCP connection with session tracking."""
        addr = writer.get_extra_info("peername")
        # Fallback session ID when client does not provide one
        session_id = "default_cli_session"
        logger.info(f"Connection from {addr} (session: {session_id})")
        self.clients.add(writer)

        try:
            while True:
                # FIX: Use readline() for proper newline-delimited message framing
                data = await reader.readline()
                if not data:
                    break
                message = data.decode().strip()
                if not message:
                    continue

                try:
                    request = json.loads(message)
                    user_input = request.get("text", "").strip()
                    source = request.get("source", "cli")

                    # Allow client to optionally specify a session_id
                    client_session = request.get("session_id", session_id)

                    # ── Built-in commands (no AI tokens spent) ──────────
                    cmd_response = self._handle_command(user_input, client_session)
                    if cmd_response is not None:
                        response = {
                            "status": "ok",
                            "response": cmd_response,
                            "session_id": client_session,
                            "workers_active": len(self.orchestrator.workers),
                        }
                        writer.write(json.dumps(response).encode() + b"\n")
                        await writer.drain()
                        continue

                    # ── Normal AI processing ─────────────────────────────
                    def on_schedule(task_data):
                        if self.add_to_scheduler(task_data):
                            self.scheduled_tasks.append(task_data)
                            self.save_tasks()

                    self.orchestrator.on_schedule_callback = on_schedule

                    start_time = time.time()
                    logger.info(f"Processing [{client_session}]: {user_input[:80]}...")

                    response_text = await asyncio.to_thread(
                        self.orchestrator.process,
                        user_input,
                        session_id=client_session,
                    )

                    duration = time.time() - start_time
                    logger.info(f"Done [{client_session}] in {duration:.2f}s")

                    # Log interaction to file
                    log_interaction(
                        session_id=client_session,
                        user_input=user_input,
                        response=response_text or "",
                        duration_s=duration,
                        source=source,
                        workers_active=len(self.orchestrator.workers),
                    )

                    response = {
                        "status": "ok",
                        "response": response_text,
                        "session_id": client_session,
                        "workers_active": len(self.orchestrator.workers),
                    }
                    writer.write(json.dumps(response).encode() + b"\n")
                    await writer.drain()
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {addr}: {e}")
                    error_resp = {"status": "error", "message": f"Invalid JSON: {e}"}
                    writer.write(json.dumps(error_resp).encode() + b"\n")
                    await writer.drain()
                except Exception as e:
                    logger.error(f"Processing error: {e}", exc_info=True)
                    error_resp = {"status": "error", "message": str(e)}
                    writer.write(json.dumps(error_resp).encode() + b"\n")
                    await writer.drain()
        finally:
            self.clients.discard(writer)
            logger.info(f"Client disconnected: {addr} (session: {session_id})")
            writer.close()

    async def run(self):
        """Start the TCP server and scheduler."""
        self.scheduler.start()
        for task in self.scheduled_tasks:
            self.add_to_scheduler(task)

        try:
            server = await asyncio.start_server(
                self.handle_client, self.host, self.port
            )
            logger.info(f"Server running on {self.host}:{self.port}")
            async with server:
                await server.serve_forever()
        except Exception as e:
            logger.critical(f"Server error: {e}")


if __name__ == "__main__":
    engine = DirigentEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
