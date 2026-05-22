# Codex Build Log

This repository was built in Codex during the MiAO challenge.

High-level interaction flow:

1. Read `CHALLENGE.md` and `CLAUDE.md`
2. Chose a zero-dependency Python implementation for speed and reliability
3. Implemented a custom agent loop with SQLite memory and tool verification
4. Added a scripted provider for deterministic demo transcripts
5. Added unit tests for memory persistence and recovery behavior
6. Generated `session1.txt` and `session2.txt` as cross-session evidence

Primary deliverables created in this session:

- `agent.py`
- `demo_sessions.py`
- `tests/test_agent.py`
- `DESIGN.md`
- `session1.txt`
- `session2.txt`
