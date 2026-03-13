#!/usr/bin/env python3
"""
DirigentAI Universal Installer
One-command installation for Linux, macOS, and Windows
"""

import os
import sys
import platform
import subprocess
import shutil
import argparse
from pathlib import Path



def print_colored(text, color):
    """Print colored text based on OS support."""
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'cyan': '\033[96m',
        'reset': '\033[0m',
    }
    
    # On Windows, colors may not work in some terminals
    if platform.system() == 'Windows' and not os.getenv('ANSICON'):
        # Try to enable ANSI escape codes on Windows 10+
        if sys.platform == 'win32':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except:
                pass
    
    # Replace Unicode box characters with ASCII if encoding fails
    display_text = text
    if platform.system() == 'Windows':
        # Simple ASCII replacements for box drawing characters
        replacements = {
            '┌': '+', '┐': '+', '└': '+', '┘': '+',
            '├': '+', '┤': '+', '┬': '+', '┴': '+',
            '─': '-', '│': '|', '┼': '+',
            '▏': '|', '┃': '|', '┅': '-',
            '┈': '-', '┉': '-', '┄': '-',
            '┆': '|', '┇': '|', '┊': '|',
            '┋': '|', '╭': '+', '╮': '+',
            '╰': '+', '╯': '+', '═': '=',
            '║': '|', '╔': '+', '╗': '+',
            '╚': '+', '╝': '+', '╟': '+',
            '╢': '+', '╤': '+', '╧': '+',
            '╬': '+'
        }
        for unicode_char, ascii_char in replacements.items():
            display_text = display_text.replace(unicode_char, ascii_char)
    
    if color in colors and sys.stdout.isatty():
        try:
            print(f"{colors[color]}{display_text}{colors['reset']}")
        except UnicodeEncodeError:
            # Fallback to ASCII-only output
            print(display_text)
    else:
        try:
            print(display_text)
        except UnicodeEncodeError:
            # ASCII fallback
            ascii_text = display_text.encode('ascii', 'replace').decode('ascii')
            print(ascii_text)

def print_header():
    title = "DirigentAI Universal Installer"
    subtitle = "One-command installation for all platforms"
    
    # Box width: 45 characters between borders
    box_width = 45
    
    # Format title line
    title_padding = box_width - len(title)
    title_line = f"│ {title}{' ' * title_padding} │"
    
    # Format subtitle line
    subtitle_padding = box_width - len(subtitle)
    subtitle_line = f"│ {subtitle}{' ' * subtitle_padding} │"
    
    print_colored("┌─────────────────────────────────────────────┐", "cyan")
    print_colored(title_line, "cyan")
    print_colored(subtitle_line, "cyan")
    print_colored("└─────────────────────────────────────────────┘", "cyan")
    print()

def print_step(step, message):
    print_colored(f"[{step}] {message}", "blue")

def print_success(message):
    print_colored(f"[SUCCESS] {message}", "green")

def print_warning(message):
    print_colored(f"[WARNING] {message}", "yellow")

def print_error(message):
    print_colored(f"[ERROR] {message}", "red")

def run_command(cmd, check=True, capture_output=False, shell=False, dry_run=False):
    """Run a command and return result."""
    print_step("EXEC", f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    
    if dry_run:
        print_step("DRY-RUN", "Would execute command (skipped)")
        if capture_output:
            return f"dry-run-output-for-{' '.join(cmd) if isinstance(cmd, list) else cmd}"
        return True
    
    try:
        if capture_output:
            result = subprocess.run(
                cmd,
                shell=shell,
                check=check,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            return result.stdout.strip()
        else:
            result = subprocess.run(
                cmd,
                shell=shell,
                check=check
            )
            return True
    except subprocess.CalledProcessError as e:
        if check:
            print_error(f"Command failed: {e}")
            return None
        return False
    except FileNotFoundError as e:
        print_error(f"Command not found: {e}")
        return None

def _print_python_install_instructions(upgrade=False):
    """Print OS-specific Python installation instructions."""
    import platform
    
    system = platform.system()
    
    if upgrade:
        print_colored("Upgrade Python using:", "yellow")
    else:
        print_colored("Install Python using:", "yellow")
    
    print()
    
    if system == "Windows":
        print_colored("Windows:", "cyan")
        print_colored("  1. Microsoft Store: Search for 'Python 3.11' or newer", "yellow")
        print_colored("  2. Official installer: https://python.org/downloads/windows/", "yellow")
        print_colored("  3. Winget: winget install Python.Python.3.11", "yellow")
        print_colored("  4. Chocolatey: choco install python311", "yellow")
        print_colored("  5. Scoop: scoop install python311", "yellow")
    
    elif system == "Darwin":  # macOS
        print_colored("macOS:", "cyan")
        print_colored("  1. Homebrew: brew install python@3.11", "yellow")
        print_colored("  2. Official installer: https://python.org/downloads/macos/", "yellow")
        print_colored("  3. MacPorts: sudo port install python311", "yellow")
    
    elif system == "Linux":
        # Try to detect distribution
        distro_info = {}
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            distro_info[key] = value.strip('"')
        except:
            pass
        
        distro_name = distro_info.get("NAME", "Linux").lower()
        
        print_colored("Linux:", "cyan")
        if "ubuntu" in distro_name or "debian" in distro_name or "pop" in distro_name or "mint" in distro_name:
            print_colored("  Ubuntu/Debian: sudo apt update && sudo apt install python3.11 python3.11-venv", "yellow")
        elif "fedora" in distro_name or "rhel" in distro_name or "centos" in distro_name:
            print_colored("  Fedora/RHEL/CentOS: sudo dnf install python3.11", "yellow")
        elif "arch" in distro_name or "manjaro" in distro_name:
            print_colored("  Arch/Manjaro: sudo pacman -S python python-pip", "yellow")
        else:
            print_colored("  Use your distribution's package manager or install from:", "yellow")
            print_colored("  https://python.org/downloads/", "yellow")
    
    else:
        print_colored("Download Python 3.11+ from: https://python.org/downloads/", "yellow")
    
    print()
    print_colored("After installing Python, run this installer again.", "yellow")
    print()

def check_python():
    """Check Python version and return python command."""
    print_step("CHECK", "Checking Python version...")
    
    # Try python3 first, then python
    python_cmds = ['python3', 'python']
    
    for cmd in python_cmds:
        try:
            result = subprocess.run(
                [cmd, '--version'],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            if result.returncode == 0:
                version_str = result.stdout.strip()
                print_step("FOUND", f"{cmd}: {version_str}")
                
                # Parse version
                import re
                match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_str)
                if match:
                    major, minor, _ = map(int, match.groups())
                    if major >= 3 and minor >= 11:
                        return cmd
                    else:
                        print_error(f"Python 3.11+ required, found {major}.{minor}")
                        print()
                        print_colored("You need to upgrade Python to version 3.11 or newer.", "yellow")
                        print()
                        _print_python_install_instructions(upgrade=True)
                        return None
        except FileNotFoundError:
            continue
    
    print_error("Python 3.11+ not found. Please install Python 3.11 or newer.")
    print()
    _print_python_install_instructions(upgrade=False)
    return None

def create_virtualenv(python_cmd, dry_run=False):
    """Create or reuse virtual environment."""
    venv_dirs = ['venv', '.venv']
    
    for venv_dir in venv_dirs:
        if os.path.exists(venv_dir):
            print_step("VENV", f"Using existing virtual environment: {venv_dir}")
            return venv_dir
    
    print_step("VENV", "Creating virtual environment...")
    venv_dir = 'venv'
    
    if dry_run:
        print_step("DRY-RUN", f"Would create virtual environment: {venv_dir}")
        return venv_dir
    
    result = run_command([python_cmd, '-m', 'venv', venv_dir], dry_run=dry_run)
    if result is False:
        print_error("Failed to create virtual environment")
        return None
    
    print_success(f"Virtual environment created: {venv_dir}")
    return venv_dir

def get_activate_command(venv_dir):
    """Get the activation command for the current shell."""
    system = platform.system()
    
    if system == "Windows":
        activate_script = os.path.join(venv_dir, "Scripts", "activate.bat")
        if os.path.exists(activate_script):
            return f"{venv_dir}\\Scripts\\activate.bat"
        else:
            # PowerShell
            return f"{venv_dir}\\Scripts\\Activate.ps1"
    else:
        # Unix/Linux/macOS
        activate_script = os.path.join(venv_dir, "bin", "activate")
        if os.path.exists(activate_script):
            return f"source {venv_dir}/bin/activate"
    
    return None

def get_venv_python(venv_dir):
    """Get Python executable in virtual environment."""
    system = platform.system()
    
    if system == "Windows":
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
        if os.path.exists(python_exe):
            return python_exe
    else:
        python_exe = os.path.join(venv_dir, "bin", "python")
        if os.path.exists(python_exe):
            return python_exe
    
    # Fallback to system python if venv python not found
    return sys.executable

def install_dependencies(venv_dir, dry_run=False):
    """Install Python dependencies."""
    python_exe = get_venv_python(venv_dir)
    
    print_step("DEPS", "Upgrading pip...")
    run_command([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'], check=False, dry_run=dry_run)
    
    print_step("DEPS", "Installing Python dependencies...")
    if run_command([python_exe, '-m', 'pip', 'install', '-r', 'requirements.txt'], dry_run=dry_run):
        print_success("Dependencies installed successfully")
        return True
    else:
        if dry_run:
            return True  # In dry-run, assume success
        print_error("Failed to install dependencies")
        return False

def install_playwright(venv_dir, dry_run=False):
    """Install Playwright browser."""
    python_exe = get_venv_python(venv_dir)
    
    print_step("PLAYWRIGHT", "Installing Playwright Chromium...")
    if dry_run:
        print_step("DRY-RUN", "Would install Playwright Chromium")
        return True
    
    if run_command([python_exe, '-m', 'playwright', 'install', 'chromium'], check=False, dry_run=dry_run):
        print_success("Playwright Chromium installed")
        return True
    else:
        print_warning("Playwright installation failed. Browser workers may not work.")
        print_warning(f"You can install manually: {python_exe} -m playwright install chromium")
        return False

def run_setup(venv_dir, dry_run=False):
    """Run DirigentAI setup wizard."""
    python_exe = get_venv_python(venv_dir)
    
    print_step("SETUP", "Running DirigentAI setup wizard...")
    print()
    print_colored("The setup wizard will:", "yellow")
    print_colored("• Create configuration files", "yellow")
    print_colored("• Ask for API keys (optional)", "yellow")
    print_colored("• Configure approved models", "yellow")
    print()
    
    if dry_run:
        print_step("DRY-RUN", f"Would run: {python_exe} main.py setup")
        print_step("DRY-RUN", "Setup would ask for API keys and create config files")
        return True
    
    try:
        subprocess.run([python_exe, 'main.py', 'setup'], check=False)
        print_success("Setup completed")
        return True
    except Exception as e:
        print_warning(f"Setup encountered issues: {e}")
        print_warning(f"You can run setup manually: {python_exe} main.py setup")
        return False

def print_summary(venv_dir, python_cmd):
    """Print installation summary."""
    activate_cmd = get_activate_command(venv_dir)
    python_exe = get_venv_python(venv_dir)
    
    print()
    print_colored("┌─────────────────────────────────────────────┐", "green")
    print_colored("│ Installation Complete!                      │", "green")
    print_colored("├─────────────────────────────────────────────┤", "green")
    print_colored("│ Next steps:                                 │", "green")
    print_colored("│                                             │", "green")
    print_colored("│ 1. Activate virtual environment:            │", "green")
    
    if activate_cmd:
        if platform.system() == "Windows":
            print_colored(f"│    {activate_cmd}                 ", "green")
        else:
            print_colored(f"│    {activate_cmd}                  ", "green")
    else:
        print_colored(f"│    Use: {python_exe} main.py ...       ", "green")
    
    print_colored("│                                             │", "green")
    print_colored("│ 2. Start DirigentAI:                        │", "green")
    print_colored(f"│    {python_exe} main.py cli                ", "green")
    print_colored("│                                             │", "green")
    print_colored("│ 3. Or run in background:                    │", "green")
    print_colored(f"│    {python_exe} main.py                    ", "green")
    print_colored("│                                             │", "green")
    print_colored("│ 4. Check configuration:                     │", "green")
    print_colored(f"│    {python_exe} main.py doctor             ", "green")
    print_colored("│                                             │", "green")
    print_colored("│ 5. Update later:                            │", "green")
    print_colored(f"│    {python_exe} main.py update             ", "green")
    print_colored("└─────────────────────────────────────────────┘", "green")
    
    print()
    print_colored("Quick start:", "cyan")
    if activate_cmd:
        if platform.system() == "Windows":
            print_colored(f"  {activate_cmd}", "yellow")
            print_colored(f"  {python_exe} main.py cli", "yellow")
        else:
            print_colored(f"  {activate_cmd}", "yellow")
            print_colored(f"  {python_exe} main.py cli", "yellow")
    else:
        print_colored(f"  {python_exe} main.py cli", "yellow")

def main():
    """Main installation process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="DirigentAI Universal Installer")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be installed without making changes")
    
    args = parser.parse_args()
    
    print_header()
    if args.dry_run:
        print_colored("DRY RUN MODE: No changes will be made", "yellow")
        print()
    
    # Check if already in a virtual environment
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print_warning("Already running inside a virtual environment")
        print_warning("Continuing with current environment...")
    
    # Check Python
    python_cmd = check_python()
    if not python_cmd:
        return 1
    
    # Create virtual environment (if not already in one)
    venv_dir = None
    if not in_venv:
        venv_dir = create_virtualenv(python_cmd, dry_run=args.dry_run)
        if not venv_dir:
            return 1
    else:
        venv_dir = os.path.basename(sys.prefix)
        print_step("VENV", f"Using current virtual environment: {venv_dir}")
    
    # Install dependencies
    if not install_dependencies(venv_dir, dry_run=args.dry_run):
        return 1
    
    # Install Playwright
    install_playwright(venv_dir, dry_run=args.dry_run)
    
    # Run setup
    run_setup(venv_dir, dry_run=args.dry_run)
    
    # Print summary
    print_summary(venv_dir, python_cmd)
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print_colored("Installation cancelled by user", "yellow")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)