import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("dirigent.interaction_log")

LOG_FILE = Path("memory/interactions.jsonl")


def log_interaction(
    session_id: str,
    user_input: str,
    response: str,
    duration_s: float,
    source: str = "cli",
    workers_active: int = 0,
) -> None:
    """
    Append one interaction to the JSONL log file.
    Each line is a self-contained JSON object.
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "session": session_id,
            "source": source,
            "user": user_input,
            "response": response,
            "duration_s": round(duration_s, 2),
            "workers_active": workers_active,
        }
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write interaction log: {e}")
