# FRI_collect

@AGENTS.md

## System of Record
- Stack: [detected at runtime by quality gate — add stack-specific tooling here]
- Commands: [add build/test/lint commands in AGENTS.md]

## Harness Hooks Active
- **SessionStart**: MCP health check
- **PreToolUse**: Security guard + Secret guard
- **PostToolUse**: Trace logger + Auto-formatter
- **Stop**: Quality gate + Context monitor

## Built-in Agents
- `code-reviewer` — security review | `pr-author` — PR drafts | `commit-helper` — commits

## Context Budget
- Delegate research to sub-agents. Compact after 30+ tool calls.
- Universal rules in AGENTS.md — keep this file under 30 lines.

## Escape Hatches
- Quality gate stuck? Retry (stop_hook_active protection).
- Security guard wrong? Use alternative command.
- Same error 3 times? Ask the human.
