# Design

I used a small custom Python agent instead of a framework to keep the control loop explicit under time pressure. The model receives three tools: `remember_fact`, `recall_context`, and `calculate`. That tool split matches the challenge requirements while keeping schemas minimal: one write tool for durable user knowledge, one read tool for personalization, and one domain tool that demonstrates judgment plus failure recovery. The chat client is provider-adaptable, so the same loop works with OpenAI and MiniMax's OpenAI-compatible Coding Plan endpoint.

Memory is stored in SQLite because it is local, durable, queryable, and easy to inspect. I keep three tables instead of dumping raw chat logs: `facts` for stable structured knowledge, `session_summaries` for end-of-session rollups, and `tool_events` for verification traces. This makes the agent selective about what it persists. Stable facts such as dietary preference are saved as facts; transient turn-by-turn reasoning is not.

Verification runs after every tool call, not just inside broad exception handling. Each tool has a deterministic acceptance rule:

- `remember_fact`: key/value must be non-empty and the stored row must match the request.
- `recall_context`: result shape must be valid, and an invalid limit is clamped to a safe default.
- `calculate`: result must be a finite number.

One concrete failure mode handled by the verification layer is malformed arithmetic text from the model, such as `12 x 8 + 4`. The first evaluation fails because `x` is not a valid Python operator. The verifier then applies a deterministic recovery step that normalizes common math phrasing (`x`, `times`, `=`) into safe symbols and retries. If that retry succeeds, the tool result is accepted with a `recovered` status; otherwise the agent returns an explicit error instead of silently continuing.

For MiniMax specifically, the loop preserves the raw assistant content in history because the model may embed hidden reasoning inside `<think>...</think>` tags during OpenAI-compatible tool use. The CLI strips those tags only for terminal display, keeping the conversation state intact without exposing the reasoning block to the user. To reduce secret-handling risk during challenge submission, the CLI also supports file-based API key loading so credentials can stay in an untracked local file outside the repo and outside the AI conversation log.
