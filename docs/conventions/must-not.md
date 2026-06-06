# Must Not

Forbidden patterns. These will be caught by review or CI.

## Code

- `console.log` / `print()` in production code — use a logger
- Commented-out code — delete it, git history preserves it
- `TODO` without a ticket number — `TODO(PROJ-123)`
- Magic numbers — name them as constants
- `catch (e) {}` — empty catch blocks that swallow errors

## Dependencies

- No direct imports across module boundaries without going through public API
- No circular imports

## Production

- No debug mode or verbose logging in production builds
- No client-side storage of sensitive tokens
