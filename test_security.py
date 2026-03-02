import asyncio
import json
import os
import sys

# Ensure the project root is in the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
sys.path.insert(0, project_root)

from core.orchestrator import Orchestrator
from agents.worker import Worker, is_command_safe, is_path_safe
from hub import DirigentEngine


async def test_unauthorized_access():
    print("\n[Test Security 1]: Unauthorized terminal access...")

    # Create worker ONLY with file_ops
    worker_file_only = Worker(
        worker_id="file_expert",
        capabilities=["file_ops"],
        description="File specialist",
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    # Instruction requiring terminal
    instruction = "List running processes in the system."

    # Run execute method
    result = worker_file_only.execute(instruction)

    print(f"Result: {result}")

    if "lack" in result.lower() or "permission" in result.lower() or "capability" in result.lower() or "Error" in result:
        print("PASS: Worker correctly refused unauthorized command.")
    else:
        print("FAIL: Worker should have refused but did something else.")


async def test_unknown_worker():
    print("\n[Test Security 2]: Delegation to unknown worker...")
    orchestrator = Orchestrator()

    # Attempt to delegate to unknown worker
    result = orchestrator.process("Greet my assistant worker_999")
    print(f"Result: {result}")

    if result and ("Error" in result or "does not exist" in result or "worker" in result.lower()):
        print("PASS: Dirigent correctly handles unknown worker.")
    else:
        print("FAIL: Dirigent should have reported unknown worker.")


async def test_invalid_schedule():
    print("\n[Test Security 3]: Invalid schedule format...")
    # FIX: Use DirigentEngine which has add_to_scheduler, not Orchestrator
    engine = DirigentEngine()

    invalid_task = {
        "task_description": "Invalid plan test",
        "schedule_type": "cron",
        "schedule_value": "every hour",
    }

    # Call add_to_scheduler on engine (not orchestrator)
    success = engine.add_to_scheduler(invalid_task)

    if not success:
        print("PASS: Scheduler rejected invalid cron format.")
    else:
        print("FAIL: Scheduler accepted invalid cron format.")


def test_command_blacklist():
    print("\n[Test Security 4]: Command blacklist...")

    dangerous_commands = [
        "rm -rf /",
        "rm -rf /*",
        "format c:",
        "shutdown -s -t 0",
        "dd if=/dev/zero of=/dev/sda",
    ]

    all_blocked = True
    for cmd in dangerous_commands:
        is_safe, reason = is_command_safe(cmd)
        if is_safe:
            print(f"  FAIL: '{cmd}' was NOT blocked!")
            all_blocked = False
        else:
            print(f"  OK: '{cmd}' blocked ({reason})")

    if all_blocked:
        print("PASS: All dangerous commands were blocked.")
    else:
        print("FAIL: Some dangerous commands were not blocked.")


def test_path_sanitization():
    print("\n[Test Security 5]: Path sanitization...")

    dangerous_paths = [
        "../../etc/passwd",
        "/etc/shadow",
        ".env",
        "C:\\Windows\\System32\\config\\SAM",
        "../../../.ssh/id_rsa",
    ]

    all_blocked = True
    for path in dangerous_paths:
        is_safe, reason = is_path_safe(path)
        if is_safe:
            print(f"  FAIL: '{path}' was NOT blocked!")
            all_blocked = False
        else:
            print(f"  OK: '{path}' blocked ({reason})")

    if all_blocked:
        print("PASS: All dangerous paths were blocked.")
    else:
        print("FAIL: Some dangerous paths were not blocked.")


def test_session_context():
    print("\n[Test Security 6]: Session isolation...")
    orchestrator = Orchestrator()

    # Create two sessions
    session_a = orchestrator.get_or_create_session("session_a")
    session_b = orchestrator.get_or_create_session("session_b")

    # They should be independent lists
    assert session_a is not session_b, "Sessions should be separate objects"
    assert len(orchestrator.list_sessions()) >= 2, "Should have at least 2 sessions"

    # Clear one shouldn't affect the other
    orchestrator.clear_session("session_a")
    assert "session_a" not in orchestrator.list_sessions()
    assert "session_b" in orchestrator.list_sessions()

    print("PASS: Sessions are properly isolated.")


async def run_security_tests():
    # Run local tests first (no API needed)
    test_command_blacklist()
    test_path_sanitization()
    test_session_context()

    # API-dependent tests
    if os.getenv("GEMINI_API_KEY"):
        await test_unauthorized_access()
        await test_unknown_worker()
        await test_invalid_schedule()
    else:
        print("\nSkipping API-dependent tests (no GEMINI_API_KEY).")

    print("\nAll security and robustness tests completed!")


if __name__ == "__main__":
    asyncio.run(run_security_tests())
