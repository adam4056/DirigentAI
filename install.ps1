# DirigentAI Installer for Windows
# One-command installation with PowerShell

Write-Host "┌─────────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "│ DirigentAI Installer                        │" -ForegroundColor Cyan
Write-Host "│ One-command installation for Windows        │" -ForegroundColor Cyan
Write-Host "└─────────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
if (([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "⚠️  Warning: Running as Administrator is not recommended." -ForegroundColor Yellow
    Write-Host "   Please run as a regular user without elevated privileges." -ForegroundColor Yellow
    exit 1
}

# Function to print colored messages
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check Python version
Write-Info "Checking Python version..."
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
}

if (-not $pythonCmd) {
    Write-Error "Python not found. Please install Python 3.11+"
    Write-Host ""
    Write-Host "You can install Python using one of these methods:" -ForegroundColor Yellow
    Write-Host "1. Microsoft Store: Search for 'Python 3.11' or newer" -ForegroundColor Yellow
    Write-Host "2. Official website: https://python.org/downloads/windows/" -ForegroundColor Yellow
    Write-Host "3. Winget: winget install Python.Python.3.11" -ForegroundColor Yellow
    Write-Host "4. Chocolatey: choco install python311" -ForegroundColor Yellow
    Write-Host "5. Scoop: scoop install python311" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing Python, run this script again." -ForegroundColor Yellow
    exit 1
}

try {
    $pythonVersion = & $pythonCmd --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get Python version"
    }
} catch {
    Write-Error "Failed to get Python version: $_"
    exit 1
}

Write-Info "Found $pythonVersion"

# Parse version
$versionMatch = [regex]::Match($pythonVersion, '(\d+)\.(\d+)\.(\d+)')
if (-not $versionMatch.Success) {
    Write-Error "Could not parse Python version from: $pythonVersion"
    exit 1
}

$major = [int]$versionMatch.Groups[1].Value
$minor = [int]$versionMatch.Groups[2].Value

if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
    Write-Error "Python 3.11+ required, but found $major.$minor"
    Write-Host ""
    Write-Host "You need to upgrade Python to version 3.11 or newer." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Install/upgrade methods:" -ForegroundColor Yellow
    Write-Host "1. Microsoft Store: Search for 'Python 3.11' or newer" -ForegroundColor Yellow
    Write-Host "2. Official website: https://python.org/downloads/windows/" -ForegroundColor Yellow
    Write-Host "3. Winget: winget install --upgrade Python.Python.3.11" -ForegroundColor Yellow
    Write-Host "4. Chocolatey: choco install python311" -ForegroundColor Yellow
    Write-Host "5. Scoop: scoop install python311" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing Python, run this script again." -ForegroundColor Yellow
    exit 1
}

# Check if virtual environment exists
$venvDir = $null
if (Test-Path "venv") {
    $venvDir = "venv"
    Write-Info "Virtual environment already exists in 'venv/'"
} elseif (Test-Path ".venv") {
    $venvDir = ".venv"
    Write-Info "Virtual environment already exists in '.venv/'"
} else {
    # Create virtual environment
    Write-Info "Creating virtual environment..."
    try {
        & $pythonCmd -m venv venv
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
        $venvDir = "venv"
        Write-Success "Virtual environment created in '$venvDir/'"
    } catch {
        Write-Error "Failed to create virtual environment: $_"
        exit 1
    }
}

# Activate virtual environment
Write-Info "Activating virtual environment..."
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    # Try Python 3.11+ venv structure
    $activateScript = Join-Path $venvDir "bin\Activate.ps1"
}

if (Test-Path $activateScript) {
    try {
        . $activateScript
        Write-Success "Virtual environment activated"
    } catch {
        Write-Warning "Could not activate virtual environment: $_"
        Write-Warning "Continuing anyway..."
    }
} else {
    Write-Warning "Could not find activation script. Continuing without activation."
    Write-Warning "You may need to activate manually: .\$venvDir\Scripts\Activate.ps1"
}

# Upgrade pip
Write-Info "Upgrading pip..."
try {
    & $pythonCmd -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip"
    }
    Write-Success "pip upgraded successfully"
} catch {
    Write-Warning "Failed to upgrade pip: $_"
}

# Install dependencies
Write-Info "Installing Python dependencies..."
try {
    & $pythonCmd -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies"
    }
    Write-Success "Dependencies installed successfully"
} catch {
    Write-Error "Failed to install dependencies: $_"
    Write-Host ""
    Write-Host "You can try installing manually:" -ForegroundColor Yellow
    Write-Host "1. Activate virtual environment: .\$venvDir\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "2. Run: pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Install Playwright browser
Write-Info "Installing Playwright Chromium..."
try {
    & $pythonCmd -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Playwright Chromium"
    }
    Write-Success "Playwright Chromium installed"
} catch {
    Write-Warning "Playwright installation failed. Browser workers may not work."
    Write-Warning "You can install it manually later with: $pythonCmd -m playwright install chromium"
}

# Run setup
Write-Info "Running DirigentAI setup wizard..."
Write-Info "This will create configuration files and ask for API keys."
Write-Host ""
try {
    & $pythonCmd main.py setup
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Setup may have encountered issues."
        Write-Warning "You can run setup manually with: $pythonCmd main.py setup"
    } else {
        Write-Success "Setup completed successfully!"
    }
} catch {
    Write-Warning "Setup failed: $_"
}

# Summary
Write-Host ""
Write-Host "┌─────────────────────────────────────────────┐" -ForegroundColor Green
Write-Host "│ Installation Complete!                      │" -ForegroundColor Green
Write-Host "├─────────────────────────────────────────────┤" -ForegroundColor Green
Write-Host "│ Next steps:                                 │" -ForegroundColor Green
Write-Host "│                                             │" -ForegroundColor Green
Write-Host "│ 1. Start DirigentAI:                        │" -ForegroundColor Green
Write-Host "│    $pythonCmd main.py cli                   │" -ForegroundColor Green
Write-Host "│                                             │" -ForegroundColor Green
Write-Host "│ 2. Or run in background:                    │" -ForegroundColor Green
Write-Host "│    $pythonCmd main.py                       │" -ForegroundColor Green
Write-Host "│                                             │" -ForegroundColor Green
Write-Host "│ 3. Check configuration:                     │" -ForegroundColor Green
Write-Host "│    $pythonCmd main.py doctor                │" -ForegroundColor Green
Write-Host "│                                             │" -ForegroundColor Green
Write-Host "│ 4. Update later:                            │" -ForegroundColor Green
Write-Host "│    $pythonCmd main.py update                │" -ForegroundColor Green
Write-Host "└─────────────────────────────────────────────┘" -ForegroundColor Green
Write-Host ""
Write-Info "To activate the virtual environment in a new PowerShell window:"
Write-Host "  .\$venvDir\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Info "To deactivate the virtual environment:"
Write-Host "  deactivate" -ForegroundColor Yellow
Write-Host ""
Write-Info "If you encounter Unicode display issues in CMD, use:"
Write-Host "  chcp 65001" -ForegroundColor Yellow
Write-Host ""