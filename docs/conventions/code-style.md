# Code Style

Formatting and naming conventions for this project.

## Naming

- Files: lowercase, hyphens for separation (`user-auth.ts`, `user_auth.py`)
- Variables: `camelCase` (JS/TS), `snake_case` (Python, Rust, Go)
- Constants: `UPPER_SNAKE_CASE`
- Functions: verb + noun (`getUser`, `fetch_data`, `parse_config`)

## Formatting

- Indentation: see `.editorconfig`
- Line length: 120 characters max
- No trailing whitespace
- File ends with one blank line

## Imports

- Group and sort: standard library → third-party → local
- No wildcard imports (`import *`, `from x import *`)
- No circular imports

## Comments

- Explain WHY, not WHAT — the code is the WHAT
- Remove commented-out code — git preserves history
- No `TODO` without a ticket reference: `TODO(PROJ-123): ...`
