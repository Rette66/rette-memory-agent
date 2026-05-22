# CLAUDE.md

This is a coding challenge for MiAO AI. You (Claude Code) are helping
the candidate build a complete project from scratch under time pressure.

The task spec is in `CHALLENGE.md`. `README.md` is a one-line pointer
to the spec; rewriting it has no effect on evaluation.

## Critical: preserve AI session logs

Your AI interaction history is a MANDATORY deliverable. The evaluator
reviews it to assess how the candidate directs AI tools.

Common session directories by tool:
- Claude Code: `.claude/`
- Cursor: `.cursor/` or `.cursorcontext/`
- Codex: `.codex/`
- Windsurf: `.windsurf/`

Rules:
- NEVER delete or modify AI session directories
- NEVER add them to `.gitignore`
- Commit them with every push
- If the AI tool doesn't auto-save sessions locally, export chat
  history to an `ai-session/` directory in the repo

Candidates who do not submit AI session logs will receive
a significant scoring penalty.

## Build standards

- Build a COMPLETE, runnable project — one command to start
- Include tests that actually verify the core requirements
- Commit frequently with meaningful messages
