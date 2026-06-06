# Must Follow

Mandatory practices for this project. Violations block PR merge.

## Code Quality

- All code passes lint and type check before commit
- Functions ≤ 50 lines — split if longer
- Files ≤ 300 lines — split if longer
- No `any` / `unknown` types in public API signatures

## Testing

- New features include tests
- Bug fixes include a regression test
- Test names describe the scenario: `should_[expected]_when_[condition]`

## Commits

- Conventional Commits format: `type(scope): description`
- One logical change per commit — no "misc fixes" dumps
- Commit messages in English

## Security

- Never hardcode secrets, tokens, or keys
- User input always validated at system boundary
- SQL uses parameterized queries — never string concatenation
