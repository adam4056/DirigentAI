DIRIGENTAI BOT README

Purpose
DirigentAI is a local-first multi-agent orchestration project. One orchestrator delegates work to workers with limited capabilities.

Main entry points
- main.py: setup wizard, config CLI, model manager, doctor command, startup entry point
- hub.py: local TCP hub on 127.0.0.1:8888
- app.py: interactive CLI client
- telegram_client.py: Telegram bridge

Core architecture
- core/config.py: loads config from config/dirigent.yaml, with legacy fallback from config/dirigent.json
- core/orchestrator.py: orchestrator logic, worker spawning, delegation, memory updates
- core/llm/factory.py: model normalization and LiteLLM client creation
- agents/worker.py: worker execution, tool dispatch, shell/file/web safety checks
- memory/: persisted long-term data

Config model
- Secrets live in .env
- Main app config lives in config/dirigent.yaml
- Example config lives in config/dirigent.yaml.example
- The app supports multiple models, but only models listed in llm_policy.approved_models may be used
- A model must also have a matching API key present in .env

Important safety rule
Never assume the system may use arbitrary models. The policy is explicit:
- one approved model -> use it everywhere
- multiple approved models -> use only those approved models
- no silent fallback to an unapproved model

Useful commands
- python main.py setup
- python main.py config
- python main.py models
- python main.py doctor
- python main.py cli
- python main.py

Doctor command
- doctor is a static diagnostics command
- it checks config presence, approved models, provider inference, normalized model routing, role mapping, worker preset routing, and env presence
- it does not make live API calls
- models without keys should be treated as UNTESTED, not OK

Files that are config vs data
- config/dirigent.yaml: editable app config
- .env: editable secrets
- memory/workers.json: persisted worker registry data
- memory/tasks.json: scheduled task data
- memory/MEMORY.md: long-term notes

Editing guidance
- Keep user-facing strings in English unless the user explicitly wants local language text
- Keep config changes aligned with the approved-model policy
- Do not introduce hidden model fallbacks
- Preserve workspace safety restrictions in agents/worker.py
- If you change config shape, update main.py setup/config CLI and README.md together
- If you change model routing, update doctor output expectations too

Documentation expectations
If behavior changes for setup, config, models, doctor, worker routing, or config format:
- update README.md
- update README_BOTS.txt
- update config/dirigent.yaml.example if relevant

Worker browser tools
- Capability: browser_ops
- Backed by tools/browser.py
- Uses Playwright headless Chromium for JS, cookies, and login flows
- Extracts cleaned text for LLM use instead of raw rendered markup
- Requires: pip install -r requirements.txt and python -m playwright install chromium

Platform compatibility
- Worker terminal commands are executed through an explicit OS-specific shell, not generic shell=True
- Windows: pwsh -> powershell -> cmd.exe
- Linux/macOS: bash -> zsh -> sh
- Browser tools are Playwright-based and intended to work on Windows, Linux, and macOS
- If the CLI visuals look broken on Windows, the terminal may need UTF-8 enabled
