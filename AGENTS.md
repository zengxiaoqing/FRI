# FRI_collect

FRI算法的整理完善和发布

## Commands

- Build: `pip install -e .[dev]`
- Test: `pytest tests/ -v`
- Lint: `ruff check src/`
- Format: `ruff format src/`
- Install with all extras: `pip install -e .[all]`
- Check types: `python -c "from fri import FRIInterpolator; print('OK')"`

## Constraints

- Never push to main — create feat/ or fix/ branches
- No secrets in code — use env vars or a vault
- Single PR ≤ 500 lines; attach verification evidence

## Behavioral Rules

Read `docs/conventions/karpathy-guidelines.md` for AI behavioral rules — think before coding, simplicity first, surgical changes, goal-driven execution.


## Workflow

1. Understand — Read code, check docs/ for architecture and conventions
2. Plan — Break task into steps, check docs/decisions/ for prior ADRs
3. Implement — Write code within constraints
4. Verify — Run quality gate before finishing
5. Document — Update docs/ if something was tricky

## Knowledge Base

| Directory | Purpose |
|-----------|---------|
| [docs/architecture/](docs/architecture/INDEX.md) | System design, tech stack, data flow |
| [docs/conventions/](docs/conventions/INDEX.md) | Coding standards, naming, patterns |
| [docs/decisions/](docs/decisions/INDEX.md) | Architecture Decision Records |

## Cross-Tool Compatibility

This file is read by: Claude Code, Cursor, GitHub Copilot, Windsurf, Codex, Reasonix Code, Kimi Code CLI, and other AI coding tools.
Tool-specific configuration lives in each tool's directory:
- **Claude Code** → `.claude/` (hooks, agents, skills, rules)
- **Reasonix Code** → `.reasonix/` (skills, memory, hooks)
- **Kimi Code CLI** → `.agents/skills/` (skills)

Do not maintain separate rule files manually — edit this file and tool-specific config as needed.
