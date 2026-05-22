# Rette Memory Agent

Rette Memory Agent is a local personal AI assistant CLI focused on durable memory, tool use, and safe recovery from failures.

Core features:

- persistent SQLite memory across sessions
- startup-loaded persona and speaking-style memory
- on-demand recall for user preferences and facts
- LLM-driven tool calling
- deterministic post-tool verification and recovery
- automatic session summaries
- first-class MiniMax Coding Plan support

## Quick start

MiniMax Coding Plan mode:

```powershell
$env:MINIMAX_API_KEY="your-token-plan-key"
python agent.py --provider minimax
```

Secret-file mode, so the key never appears in chat logs or committed files:

```powershell
$env:MINIMAX_API_KEY_FILE="C:\Users\you\.miao-secrets\minimax.key"
$env:MIAO_HTTP_TIMEOUT="180"
python agent.py --provider minimax
```

If you are using the China endpoint, set:

```powershell
$env:MINIMAX_BASE_URL="https://api.minimaxi.com/v1"
```

OpenAI mode:

```powershell
$env:OPENAI_API_KEY="your-key"
python agent.py
```

OpenAI also supports file-based secrets:

```powershell
$env:OPENAI_API_KEY_FILE="C:\Users\you\.miao-secrets\openai.key"
python agent.py
```

Local demo mode:

```powershell
python demo_sessions.py
Get-Content .\session1.txt
Get-Content .\session2.txt
```

## Single-command startup

```powershell
python agent.py
```

Optional flags:

```powershell
python agent.py --provider scripted --reset-memory
python agent.py --provider minimax
python agent.py --provider scripted --script-file demo_inputs/session1.in
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Files

- `agent.py`: CLI, memory store, tool loop, verification pipeline
- `demo_sessions.py`: reproducible local demo runner
- `DESIGN.md`: short design rationale
- `TODO.md`: future memory roadmap
- `session1.txt`, `session2.txt`: sample cross-session memory transcripts

## MiniMax notes

- `--provider minimax` uses the official OpenAI-compatible chat endpoint.
- The agent preserves raw assistant messages in history so MiniMax tool-use rounds keep their hidden `<think>...</think>` context intact.
- The terminal display strips those `<think>` tags before printing the final answer to the user.
- `MINIMAX_API_KEY_FILE` is supported, so you can keep the real key in an untracked local file outside the repo.
- If MiniMax is slow on a tool-heavy turn, increase `MIAO_HTTP_TIMEOUT` (for example `180`) instead of editing code.
