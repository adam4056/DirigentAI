# Contributing

Thanks for contributing to DirigentAI.

## Before You Start

- Open an issue for large changes before starting implementation.
- Keep changes focused. Avoid mixing refactors with unrelated fixes.
- Treat the project as experimental. Prefer clear, safe behavior over clever behavior.

## Development Setup

1. Install Python 3.11+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install the Playwright browser runtime if you want browser workers:
   ```bash
   python -m playwright install chromium
   ```
4. Create your local environment:
   ```bash
   python main.py setup
   ```
5. Run static validation:
   ```bash
   python main.py doctor
   ```

## Coding Guidelines

- Keep the repo ASCII-first unless a file already needs Unicode.
- Do not silently enable models or providers the user did not approve.
- Keep worker capabilities explicit and policy-driven.
- Prefer small patches with clear intent.

## Testing

At minimum, run:

```bash
python -m py_compile main.py app.py hub.py agents/worker.py core/config.py core/orchestrator.py core/llm/litellm_client.py tools/browser.py
```

If your change affects behavior, also run the relevant local flow manually, for example:

- `python main.py setup`
- `python main.py doctor`
- `python main.py cli`

## Pull Requests

Include:

- What changed
- Why it changed
- How you tested it
- Any known risks or follow-up work

## Security

If you find a security issue, do not open a public issue first. See `SECURITY.md`.
