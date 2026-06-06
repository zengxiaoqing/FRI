# FRInterp — Knowledge Base

Agent-readable project memory. Start here for context on any task.

## Project Directories

| Directory | Purpose | Type |
|-----------|---------|------|
| `src/` | Source code | Input |
| `tests/` | Test suites | Input |
| `data/raw/` | Original data — read only | Input |
| `data/processed/` | Cleaned/transformed data | Generated |
| `references/` | External docs, papers, requirements | Input |
| `output/` | Reports, figures, exports | Generated |

## Knowledge Base Navigation

| Directory | Purpose | When to Load |
|-----------|---------|-------------|
| [architecture/](architecture/INDEX.md) | System design, tech stack, data flow | Before any architectural change |
| [conventions/](conventions/INDEX.md) | Coding standards, naming, patterns | Before writing code |
| [decisions/](decisions/INDEX.md) | Architecture Decision Records | Before revisiting prior decisions |

## Rules of This Knowledge Base

- Each directory has an INDEX.md — read it first, not the full files
- Documents ≤ 150 lines each — split if longer
- Stale docs worse than no docs — delete or mark `[OUTDATED]`
- Update after any surprising or non-obvious change
