#!/usr/bin/env bash

set -e  # Exit on any error

echo "┌─────────────────────────────────────────────┐"
echo "│ DirigentAI Installer                        │"
echo "│ One-command installation for Linux/macOS    │"
echo "└─────────────────────────────────────────────┘"
echo

# Check if running as root (not recommended)
if [[ $EUID -eq 0 ]]; then
    echo "⚠️  Warning: Running as root is not recommended."
    echo "   Please run as a regular user without sudo."
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check Python version
print_info "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    print_error "Python not found. Please install Python 3.11+"
    echo ""
    echo "To install Python, follow the instructions for your operating system:"
    echo ""
    
    # Detect OS and provide specific instructions
    OS_TYPE="unknown"
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS_TYPE="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS_TYPE="macos"
    elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        OS_TYPE="windows"
    fi
    
    if [[ "$OS_TYPE" == "linux" ]]; then
        # Try to detect distribution
        if [[ -f /etc/os-release ]]; then
            source /etc/os-release
            case $ID in
                ubuntu|debian|pop|linuxmint)
                    echo "For $NAME, use:"
                    echo "  sudo apt update && sudo apt install python3.11 python3.11-venv"
                    ;;
                fedora|rhel|centos)
                    echo "For $NAME, use:"
                    echo "  sudo dnf install python3.11"
                    ;;
                arch|manjaro)
                    echo "For $NAME, use:"
                    echo "  sudo pacman -S python python-pip"
                    ;;
                *)
                    echo "For Linux, install Python 3.11 from your package manager or from:"
                    echo "  https://python.org/downloads/"
                    ;;
            esac
        else
            echo "For Linux, install Python 3.11 from:"
            echo "  https://python.org/downloads/"
        fi
    elif [[ "$OS_TYPE" == "macos" ]]; then
        echo "For macOS, you can install Python using:"
        echo "  1. Homebrew: brew install python@3.11"
        echo "  2. Official installer: https://python.org/downloads/macos/"
        echo "  3. MacPorts: sudo port install python311"
    elif [[ "$OS_TYPE" == "windows" ]]; then
        echo "For Windows, download Python from:"
        echo "  https://python.org/downloads/windows/"
        echo ""
        echo "Or use winget: winget install Python.Python.3.11"
        echo "Or use Chocolatey: choco install python311"
    else
        echo "Download Python 3.11+ from: https://python.org/downloads/"
    fi
    
    echo ""
    echo "After installing Python, run this script again."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
print_info "Found Python $PYTHON_VERSION"

# Check if Python version is >= 3.11
IFS='.' read -ra VERSION_PARTS <<< "$PYTHON_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}

if [[ $MAJOR -lt 3 ]] || ( [[ $MAJOR -eq 3 ]] && [[ $MINOR -lt 11 ]] ); then
    print_error "Python 3.11+ required, but found $PYTHON_VERSION"
    echo ""
    echo "You need to upgrade Python to version 3.11 or newer."
    echo "Download the latest version from: https://python.org/downloads/"
    echo ""
    echo "On macOS with Homebrew: brew upgrade python"
    echo "On Ubuntu/Debian: sudo apt install python3.11"
    echo "On Fedora: sudo dnf install python3.11"
    echo ""
    echo "After upgrading Python, run this script again."
    exit 1
fi

# Check if virtual environment exists
if [[ -d "venv" ]] || [[ -d ".venv" ]]; then
    print_info "Virtual environment already exists"
    if [[ -d "venv" ]]; then
        VENV_DIR="venv"
    else
        VENV_DIR=".venv"
    fi
else
    # Create virtual environment
    print_info "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    VENV_DIR="venv"
    print_success "Virtual environment created in '$VENV_DIR/'"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux"* ]]; then
    source "$VENV_DIR/bin/activate"
else
    print_error "Unsupported OS: $OSTYPE"
    exit 1
fi

# Upgrade pip
print_info "Upgrading pip..."
$PYTHON_CMD -m pip install --upgrade pip

# Install dependencies
print_info "Installing Python dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt

if [[ $? -eq 0 ]]; then
    print_success "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Install Playwright browser
print_info "Installing Playwright Chromium..."
$PYTHON_CMD -m playwright install chromium

if [[ $? -eq 0 ]]; then
    print_success "Playwright Chromium installed"
else
    print_warning "Playwright installation failed. Browser workers may not work."
    print_warning "You can install it manually later with: $PYTHON_CMD -m playwright install chromium"
fi

# Run setup
print_info "Running DirigentAI setup wizard..."
print_info "This will create configuration files and ask for API keys."
echo
$PYTHON_CMD main.py setup

if [[ $? -eq 0 ]]; then
    print_success "Setup completed successfully!"
else
    print_warning "Setup may have encountered issues."
    print_warning "You can run setup manually with: $PYTHON_CMD main.py setup"
fi

# Summary
echo
echo "┌─────────────────────────────────────────────┐"
echo "│ Installation Complete!                      │"
echo "├─────────────────────────────────────────────┤"
echo "│ Next steps:                                 │"
echo "│                                             │"
echo "│ 1. Start DirigentAI:                        │"
echo "│    $PYTHON_CMD main.py cli                  │"
echo "│                                             │"
echo "│ 2. Or run in background:                    │"
echo "│    $PYTHON_CMD main.py                      │"
echo "│                                             │"
echo "│ 3. Check configuration:                     │"
echo "│    $PYTHON_CMD main.py doctor               │"
echo "│                                             │"
echo "│ 4. Update later:                           │"
echo "│    $PYTHON_CMD main.py update               │"
echo "└─────────────────────────────────────────────┘"
echo
print_info "To activate the virtual environment in a new terminal:"
echo "  source $VENV_DIR/bin/activate"
echo
print_info "To deactivate the virtual environment:"
echo "  deactivate"
echo