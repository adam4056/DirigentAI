# DirigentAI

An autonomous agentic system modeled as a **digital firm** with a hierarchical CEO → Workers structure. Powered by **Google Gemini** with native Function Calling.

## Quick Start

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Configure:**
```bash
cp .env.example .env
# Edit .env and fill in your Gemini API key (and optionally Telegram token)
```

**3. Start:**
```bash
# Interactive CLI
python main.py cli

# Background mode (Hub + Telegram only)
python main.py

# First-time setup wizard
python main.py onboard
```

## Architecture

```
User (CLI / Telegram)
        |
   [Hub Engine]  ← TCP server on :8888, APScheduler
        |
  [Orchestrator]  ← CEO brain (Gemini + Function Calling)
        |
   [Workers]  ← Specialized agents with capability-gated tools
```

| Component | Role |
|-----------|------|
| **Hub** (`hub.py`) | Headless TCP server, task scheduler, session routing |
| **Orchestrator** (`core/orchestrator.py`) | CEO — delegates tasks, hires workers, manages memory |
| **Worker** (`agents/worker.py`) | Executes technical work within granted capabilities |
| **Telegram Bridge** (`telegram_client.py`) | Forwards messages from Telegram to Hub |
| **CLI Client** (`app.py`) | Interactive terminal client |

## Memory System

Three-tier memory architecture:

| Tier | Storage | Scope |
|------|---------|-------|
| **Session context** | RAM (per client) | Conversation history within a session |
| **Specialist registry** | `memory/workers.json` | Hired permanent workers (survives restarts) |
| **Strategic notepad** | `memory/MEMORY.md` | Long-term facts and project knowledge |

## Worker Capabilities

Workers are created with specific capability grants. They only receive tool definitions matching their permissions:

| Capability | Tools |
|------------|-------|
| `terminal` | `run_terminal_command` |
| `file_ops` | `write_to_file`, `read_file`, `list_directory` |
| `web_ops`  | `fetch_url` |

## Security

- **Capability isolation** — workers cannot use tools outside their granted permissions
- **Command blacklist** — dangerous shell commands are blocked (`rm -rf /`, `format c:`, `shutdown`, fork bombs, etc.)
- **Path sanitization** — file operations are restricted to the workspace directory; directory traversal and sensitive files (`.env`, `.ssh`, etc.) are blocked
- **Telegram allowlist** — only users with IDs listed in `TELEGRAM_ALLOWED_USER_IDS` can communicate with the system
- **TCP on localhost only** — Hub listens on `127.0.0.1:8888` by default

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here      # optional
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321         # optional
```

Get your Gemini API key at [Google AI Studio](https://aistudio.google.com).

## Running Tests

```bash
# Robustness tests (no API key needed for most)
python test_robustness.py

# Security tests
python test_security.py
```

## Disclaimer

DirigentAI is experimental software. Automatically running terminal commands via an LLM carries inherent risk. By using this system you agree that the author is not responsible for any damages caused by its operation.

## License

MIT
