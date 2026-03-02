import sys
import os
import subprocess
import time
import socket
import signal
from colorama import init, Fore, Style

init()

# List of running processes for later cleanup
processes = []


def print_banner():
    banner = f"""
{Fore.CYAN}    ____  _      _                      __      ___    ____
   / __ \(_)____(_)____ _ ___   ____   / /_    /   |  /  _/
  / / / / / ___/ / / __ `// _ \ / __ \ / __/   / /| |  / /  
 / /_/ / / /  / / / /_/ //  __// / / // /_    / ___ | _/ /   
/_____/_/_/  /_/_/\__, / \___//_/ /_/ \__/   /_/  |_|/___/   
                 /____/                                      
{Style.RESET_ALL}"""
    print(banner)


def is_port_in_use(port):
    """Checks if the Engine is already running on the given port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_component(script_name, label, hidden=True):
    """Starts a component as a background process."""
    print(f"{Fore.CYAN}[System]: Starting {label}...{Style.RESET_ALL}")

    flags = 0
    if hidden and os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen([sys.executable, script_name], creationflags=flags)
    processes.append(proc)
    return proc


def cleanup(sig=None, frame=None):
    """Shuts down all running processes on exit."""
    print(f"\n{Fore.RED}[System]: Terminating all components...{Style.RESET_ALL}")
    for proc in processes:
        try:
            proc.terminate()
        except:
            pass
    sys.exit(0)


# Catch Ctrl+C
signal.signal(signal.SIGINT, cleanup)


def onboard():
    print_banner()
    print(f"{Fore.YELLOW}=== DirigentAI Onboarding ==={Style.RESET_ALL}\n")
    print(
        f"{Fore.RED}WARNING:{Style.RESET_ALL} Do you agree to the autonomous management of your system by DirigentAI?"
    )
    agreement = (
        input(f"Type {Fore.GREEN}'yes'{Style.RESET_ALL} to continue: ").strip().lower()
    )
    if agreement != "yes":
        sys.exit(0)

    gemini_key = input(f"Enter Gemini API Key: ").strip()
    tg_token = input(f"Enter Telegram Token (optional): ").strip()
    allowed_ids = input(f"Enter Telegram User IDs (optional, comma-separated): ").strip()

    with open(".env", "w") as f:
        f.write(f"GEMINI_API_KEY={gemini_key}\n")
        if tg_token:
            f.write(f"TELEGRAM_BOT_TOKEN={tg_token}\n")
        if allowed_ids:
            f.write(f"TELEGRAM_ALLOWED_USER_IDS={allowed_ids}\n")

    print(f"\n{Fore.GREEN}✓ Settings saved to .env!{Style.RESET_ALL}")


def run_base(with_cli=False):
    """Main startup logic."""
    print_banner()

    # 1. Start Hub (if not running)
    if not is_port_in_use(8888):
        start_component("hub.py", "Hub Engine")
        # Wait for port initialization
        for _ in range(10):
            if is_port_in_use(8888):
                break
            time.sleep(1)
    else:
        print(f"{Fore.GREEN}[System]: Hub Engine already running in background.{Style.RESET_ALL}")

    # 2. Start Telegram Ghost (if token in .env)
    from dotenv import load_dotenv

    load_dotenv()
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        start_component("telegram_client.py", "Telegram Ghost")
    else:
        print(
            f"{Fore.YELLOW}[System]: Telegram token missing, starting without Telegram.{Style.RESET_ALL}"
        )

    # 3. Interaction or Waiting
    if with_cli:
        print(f"{Fore.YELLOW}[System]: Opening CLI interface...{Style.RESET_ALL}")
        try:
            subprocess.run([sys.executable, "app.py"])
        finally:
            cleanup()
    else:
        print(f"\n{Fore.GREEN}[System]: Firm is ONLINE (Hub + Telegram).{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Press Ctrl+C to exit.{Style.RESET_ALL}\n")
        # Keep main process alive
        while True:
            time.sleep(60)


if __name__ == "__main__":
    if not os.path.exists(".env") and (len(sys.argv) < 2 or sys.argv[1] != "onboard"):
        onboard()

    if len(sys.argv) < 2:
        run_base(with_cli=False)
    elif sys.argv[1] == "cli":
        run_base(with_cli=True)
    elif sys.argv[1] == "onboard":
        onboard()
    else:
        print(f"Unknown command. Use: python main.py [cli|onboard]")
