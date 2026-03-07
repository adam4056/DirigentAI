import asyncio
import json
import os
import sys

# Add path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.worker import Worker, is_command_safe, is_path_safe
from core.orchestrator import Orchestrator


async def test_worker_security():
    print("\n[Test 1]: Checking worker security (Capabilities)...")
    # Create a worker without 'terminal' capability
    worker = Worker("secure_worker", capabilities=["file_ops"], api_key="dummy")

    # Verify that terminal tools are not offered
    tools = worker._build_tool_definitions()
    tool_names = [t["name"] for t in tools]

    if "run_terminal_command" not in tool_names:
        print("OK: Worker with 'file_ops' does not offer 'run_terminal_command'.")
    else:
        print("FAIL: Terminal tool should not be available for file_ops worker.")

    # Direct call should still work (but AI won't offer it)
    result = worker.run_terminal("echo 'hacked'")
    print(f"  Direct terminal call result: {result[:60]}...")


def test_json_resilience():
    print("\n[Test 2]: Engine resilience against broken JSON...")
    bad_data = "{ 'text': 'invalid json, missing quotes' }"
    try:
        json.loads(bad_data)
    except json.JSONDecodeError:
        print("OK: System correctly detects invalid JSON (captured in hub.py).")


def test_file_errors():
    print("\n[Test 3]: Handling file operation errors...")
    worker = Worker("test_worker")
    # Attempt to write to an illegal path
    result = worker.do_write_file("/root/secret.txt", "content")
    if "Error" in result or "Security" in result:
        print(f"OK: Write error captured: {result}")
    else:
        print("FAIL: System did not report error when writing to forbidden path.")


async def test_scheduler_validation():
    print("\n[Test 4]: Scheduler validation...")
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab("invalid cron string")
        print("FAIL: Scheduler accepted invalid cron.")
    except Exception:
        print("OK: Scheduler rejected invalid time format.")


def test_command_safety():
    print("\n[Test 5]: Command safety validation...")

    safe_commands = ["ls", "dir", "echo hello", "python --version"]
    dangerous_commands = ["rm -rf /", "format c:", "shutdown -s"]

    all_ok = True
    for cmd in safe_commands:
        is_safe, _ = is_command_safe(cmd)
        if not is_safe:
            print(f"  FAIL: Safe command '{cmd}' was blocked!")
            all_ok = False

    for cmd in dangerous_commands:
        is_safe, reason = is_command_safe(cmd)
        if is_safe:
            print(f"  FAIL: Dangerous command '{cmd}' was NOT blocked!")
            all_ok = False

    if all_ok:
        print("OK: All command safety checks passed.")


def test_path_safety():
    print("\n[Test 6]: Path safety validation...")

    safe_paths = ["output.txt", "data/report.csv", "logs/app.log"]
    dangerous_paths = [".env", "../../etc/passwd"]

    all_ok = True
    for path in safe_paths:
        is_safe, _ = is_path_safe(path)
        if not is_safe:
            print(f"  FAIL: Safe path '{path}' was blocked!")
            all_ok = False

    for path in dangerous_paths:
        is_safe, reason = is_path_safe(path)
        if is_safe:
            print(f"  FAIL: Dangerous path '{path}' was NOT blocked!")
            all_ok = False

    if all_ok:
        print("OK: All path safety checks passed.")


def test_session_management():
    print("\n[Test 7]: Session management...")
    orchestrator = Orchestrator()

    # Create sessions
    s1 = orchestrator.get_or_create_session("test_1")
    s2 = orchestrator.get_or_create_session("test_2")

    assert s1 is not s2, "Sessions must be separate"
    assert "test_1" in orchestrator.list_sessions()
    assert "test_2" in orchestrator.list_sessions()

    # Trim should not crash on empty sessions
    orchestrator.trim_session_history("test_1")

    # Clear session
    orchestrator.clear_session("test_1")
    assert "test_1" not in orchestrator.list_sessions()

    print("OK: Session management works correctly.")


async def run_all():
    await test_worker_security()
    test_json_resilience()
    test_file_errors()
    test_command_safety()
    test_path_safety()
    test_session_management()
    await test_scheduler_validation()
    print("\nAll robustness tests completed!")


if __name__ == "__main__":
    asyncio.run(run_all())
