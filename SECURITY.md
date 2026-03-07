# Security Policy

## Status

DirigentAI is currently experimental and not intended for high-assurance or production-critical use.

The project can execute terminal, file, and browser actions through AI workers. Review all behavior carefully before using it on a machine that matters.

## Supported Scope

Please report issues related to:

- Command execution safety
- File access restrictions
- Secret leakage
- Model/provider policy bypasses
- Unsafe browser automation behavior
- Session or memory exposure

## Reporting

Please report security issues privately to the maintainer before opening a public issue.

Include:

- A short description of the issue
- Impact
- Reproduction steps
- Suggested mitigation, if known

## Operational Guidance

Until the project matures further:

- Run it only on systems you control
- Use low-privilege environments where possible
- Keep API keys scoped and revocable
- Review generated commands before trusting them in sensitive contexts
