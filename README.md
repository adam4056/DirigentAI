# DirigentAI

DirigentAI is a local-first multi-agent orchestration system. One orchestrator delegates work to capability-scoped workers for coding, research, analysis, system tasks, and browser-driven web workflows.

It is designed for people who want a practical agent runtime on their own machine with explicit model approval, CLI-first setup, persistent memory, and optional Telegram access.

## What It Does

- Runs one orchestrator plus multiple specialized workers
- Supports multiple LLM providers through LiteLLM
- Uses an explicit approved-model policy
- Provides guided setup from the terminal
- Stores config in YAML and secrets in `.env`
- Includes browser-capable workers for JavaScript-heavy websites
- Keeps long-term memory, workers, and tasks on disk

## Current Status

DirigentAI is experimental software.

It is usable for local workflows, but it is not production-ready and should be treated as a controlled local tool rather than a fully hardened autonomous system.

## Core Principles

- Local-first: config, memory, workers, and tasks live on your machine
- Explicit model policy: only approved models may be used
- No silent model fallback: additional API keys do not automatically unlock hidden model use
- Capability-based workers: tools are exposed based on worker permissions

## Installation

### Requirements

- Python 3.11+
- One or more API keys for the providers you want to use
- Playwright Chromium for browser-capable workers

### 1. Clone the repository

```bash
git clone https://github.com/adam4056/DirigentAI.git
cd DirigentAI
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install the Playwright browser

```bash
python -m playwright install chromium
```

### 4. Run guided setup

```bash
python main.py setup
```

The setup wizard will:
- create `.env`
- create `config/dirigent.yaml`
- offer a Quick setup mode with one provider and one recommended model
- offer an Advanced setup mode with multiple providers and custom role mapping
- create a safe approved-model policy from those choices

### 5. Start the app

```bash
python main.py cli
```

That starts the local hub and opens the interactive CLI client.

## First Run Flow

### Recommended path

```bash
python main.py setup   # choose Quick setup unless you need multi-model routing immediately
python main.py doctor
python main.py cli
```

### If you want to edit config later

```bash
python main.py config
python main.py models
```

## CLI Commands

```bash
python main.py setup    # first-run onboarding wizard
python main.py config   # edit config and .env from CLI
python main.py models   # manage approved models and role mapping
python main.py doctor   # static diagnostics for config, model routing, and env readiness
python main.py cli      # start hub and open the interactive CLI client
python main.py          # start hub in background mode
```

## How Model Approval Works

DirigentAI only uses models that are explicitly approved in `llm_policy.approved_models` and that have a matching API key available.

This means:
- one approved model with one key -> that model is used everywhere
- multiple approved models -> only those approved models may be used
- no unapproved model is selected silently

This is a deliberate safety and cost-control rule.

## Configuration Files

DirigentAI uses:
- `.env` for API keys and secrets
- `config/dirigent.yaml` for application configuration
- `config/dirigent.yaml.example` as an example config

Persistent runtime data lives in:
- `memory/workers.json`
- `memory/tasks.json`
- `memory/MEMORY.md`

## Browser Workers

DirigentAI can use headless browser workers for dynamic websites.

These workers:
- support JavaScript-heavy pages
- preserve cookies and session state
- can be used for login flows and multi-step browsing
- extract cleaned text for LLM use instead of raw page markup

This requires Playwright Chromium to be installed.

## Platform Compatibility

DirigentAI is intended to run on Windows, Linux, and macOS.

Current compatibility model:
- terminal worker tools choose the shell explicitly per platform
- Windows prefers `pwsh`, then `powershell`, then `cmd.exe`
- Linux and macOS prefer `bash`, then `zsh`, then `sh`
- browser worker tools use Playwright headless Chromium across all supported platforms

Notes:
- on Linux, Playwright may require additional system packages depending on the distro
- on macOS and Linux, terminal commands should use POSIX shell syntax
- on Windows, terminal commands should use PowerShell or CMD-compatible syntax
- if your Windows terminal renders Unicode badly, switch to UTF-8 before running the CLI

## Using `doctor`

`python main.py doctor` performs static diagnostics.

It checks:
- whether `.env` exists
- whether `config/dirigent.yaml` exists
- approved models and inferred providers
- normalized model strings used for LiteLLM routing
- role mapping resolution
- worker preset model resolution
- which required environment variables are configured

Important:
- `doctor` does not send live API requests
- models without configured keys are marked `UNTESTED`, not `OK`
- custom model IDs are treated with higher risk than curated presets

## Troubleshooting

### `LLM Provider NOT provided`

Run:

```bash
python main.py doctor
```

This usually means a provider/model string needs normalization or the configured model is not valid for the selected provider.

### Browser tools do not work

Make sure you installed Playwright Chromium:

```bash
python -m playwright install chromium
```

### The CLI shows broken Unicode characters on Windows

Use UTF-8 before launch:

```powershell
chcp 65001
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
python main.py cli
```

### Telegram should not start

If `TELEGRAM_BOT_TOKEN` is empty, the Telegram bridge is skipped automatically.

## Security Notes

This project can execute terminal and file operations through AI workers. Treat it as experimental software.

Current safety controls include:
- capability-gated worker tools
- shell command blacklist
- workspace path restrictions
- Telegram allowlist
- explicit approved-model policy

You should still run it only on a machine and workspace you control.

## Architecture

```text
User (CLI / Telegram)
        |
   [Hub Engine]      TCP server on 127.0.0.1:8888
        |
   [Orchestrator]    Main planner and delegation layer
        |
   [Workers]         Capability-scoped task executors
```

## Project Structure

```text
app.py                  interactive CLI client
main.py                 setup, config manager, doctor, startup entry point
hub.py                  local hub server and scheduler
telegram_client.py      Telegram bridge
core/orchestrator.py    orchestrator logic
core/config.py          YAML config loader and model policy
core/llm/factory.py     LiteLLM model routing and normalization
agents/worker.py        worker implementation and tool safety
tools/browser.py        headless browser support for worker web tasks
config/dirigent.yaml.example
memory/                 long-term memory and persisted state
```

## Tests

These are currently smoke/manual test scripts, not a full automated pytest suite.

```bash
python tests/test_init.py
python tests/test_robustness.py
python tests/test_security.py
python tests/test_end_to_end.py
```

Optional manual audit script:

```bash
python tests/manual_autonomy_audit.py
```

## Community Files

- `LICENSE`: MIT
- `CONTRIBUTING.md`: contributor workflow and testing expectations
- `SECURITY.md`: private security reporting guidance

## Help

If you publish this on GitHub today, the minimum support flow I recommend is:
- tell users to start with `python main.py setup`
- tell users to run `python main.py doctor` before filing an issue
- ask users to include their OS, Python version, selected provider, and the failing model ID
- ask users to redact API keys and secrets from logs

A good issue report should include:
- what command they ran
- what provider and model they configured
- what they expected
- what actually happened
- relevant CLI output from `doctor`

## License

MIT
