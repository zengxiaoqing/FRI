# CLAUDE.md Filling Guide

How to turn the template placeholders into an effective agent entry point.

## Commands Section

Replace `[add build command]` with exact CLI invocations the agent should use.

**Good:**
```markdown
- Build: `make build`
- Test: `pytest tests/ -v --cov=src/`
- Lint: `ruff check src/ tests/`
```

**Bad:**
```markdown
- Build: use webpack or whatever
- Test: run tests
```

Rules:
- One command per line — no "or", no alternatives
- Use exact flags — the agent will copy-paste them
- If a command needs setup first, include it: `source .venv/bin/activate && pytest`
- Commands that auto-fix should be marked: `ruff check --fix src/`

## Constraints Section

Add project-specific rules. These constrain the agent's behavior.

**Good constraints:**
```markdown
- API endpoints must return JSON:API format
- All DB queries go through repository layer, never direct SQL in routes
- Feature flags use GrowthBook, check `isEnabled()` before new code paths
```

**Bad constraints:**
```markdown
- Write good code
- Follow best practices
```

Rules:
- Each constraint must be verifiable — you can look at code and say yes/no
- Prefer "must" over "should"
- Reference real project infrastructure (specific libraries, patterns, services)

## Behavioral Rules

The Karpathy guidelines at `.claude/rules/karpathy-guidelines.md` are defaults.
Add project-specific behavioral rules only if they override or extend defaults.

Examples:
- "Prefer `Result<T, E>` over exceptions for domain logic"
- "Always add a changeset file with new features"
- "Use `@deprecated` annotation instead of removing old API methods"

## Keep It Under 60 Lines

CLAUDE.md is loaded every session. Every line costs tokens. Cut:
- Explanations of what the project does (that's in README.md)
- Setup instructions (that's in README.md)
- Lists of every dependency (the agent can read package.json/pyproject.toml)
- "Remember to..." reminders (make them constraints or rules instead)

## After Filling

1. Run `claude` and ask: "Read CLAUDE.md and tell me what you know about this project"
2. If the agent misses something important, add it
3. If the agent repeats something obvious, remove it
4. Iterate — CLAUDE.md is living documentation, not a one-time write
