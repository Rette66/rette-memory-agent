# Personal AI Agent with Persistent Memory, Tool Use & Verification Pipeline

## Challenge / 编程挑战

Build a fully functional personal AI agent CLI that learns and adapts across sessions. The agent must maintain persistent user memory (preferences, facts, interaction history), execute multi-step tool calls, and include a self-verification layer that catches and recovers from tool failures — all runnable with a single command.

**Scenario:** You are building the core loop of MiAO's personal AI agent. A user interacts with the agent over multiple sessions, and the agent must become progressively more useful by remembering what it has learned. Unlike a stateless chatbot, this agent accumulates structured knowledge about the user and uses it to personalize responses and tool calls.

**What to build:**
1. A CLI agent (TypeScript or Python) backed by an LLM (OpenAI, Anthropic, or any available model) with a persistent memory store (file-based or SQLite is fine — no cloud DB required).
2. At least **3 tools** the agent can invoke: (a) `remember_fact` — stores a structured fact about the user, (b) `recall_context` — retrieves relevant memories given a query, (c) one domain tool of your choice (e.g., web search, calculator, text classifier, local file reader — pick something that shows judgment).
3. A **verification layer**: after every tool call, the agent runs a deterministic check (schema validation, result sanity check, retry logic) before accepting the tool output. If verification fails, the agent must attempt recovery (retry, fallback, or explain failure) rather than silently continuing.
4. A **session summary**: at the end of each session, the agent auto-generates a structured summary of what it learned about the user and appends it to the memory store.
5. A short `DESIGN.md` (< 400 words) explaining: your tool design decisions, how you structured memory, and one specific failure mode your verification layer handles.

**Success demo:** Run the agent for two separate sessions. In session 2, the agent demonstrably uses information from session 1 without being told — show this in a recorded terminal output (`session1.txt`, `session2.txt`) committed to the repo.

---

构建一个完整可运行的个人 AI Agent CLI，能够跨会话持久化学习和自适应。Agent 必须维护持久化用户记忆（偏好、事实、交互历史），执行多步工具调用，并包含一个自验证层来捕获并从工具失败中恢复 —— 所有功能通过一条命令即可启动。

**场景：** 你正在构建 MiAO 个人 AI Agent 的核心循环。用户在多个会话中与 Agent 交互，Agent 必须通过记住所学内容变得越来越有用。与无状态聊天机器人不同，该 Agent 会积累关于用户的结构化知识，并用其个性化响应和工具调用。

**需要构建的内容：**
1. 一个由 LLM（OpenAI、Anthropic 或任意可用模型）驱动的 CLI Agent（TypeScript 或 Python），配备持久化记忆存储（文件或 SQLite 即可，无需云数据库）。
2. Agent 至少可调用 **3 个工具**：(a) `remember_fact` —— 存储关于用户的结构化事实，(b) `recall_context` —— 根据查询检索相关记忆，(c) 一个你自行选择的领域工具（例如网络搜索、计算器、文本分类器、本地文件读取器 —— 选择能体现判断力的工具）。
3. **验证层**：每次工具调用后，Agent 在接受工具输出前运行确定性检查（schema 验证、结果合理性检查、重试逻辑）。如果验证失败，Agent 必须尝试恢复（重试、降级或解释失败），而不是静默继续。
4. **会话摘要**：每个会话结束时，Agent 自动生成关于用户所学内容的结构化摘要，并追加到记忆存储中。
5. 一份简短的 `DESIGN.md`（< 400 词），说明：你的工具设计决策、如何构建记忆结构，以及你的验证层处理的一个具体失败场景。

**成功演示：** 运行 Agent 进行两次独立会话。在第 2 次会话中，Agent 在没有被告知的情况下明显使用了第 1 次会话的信息 —— 将终端输出记录（`session1.txt`、`session2.txt`）提交到仓库中作为证明。

## Requirements / 需求

- Single-command startup (e.g., `npm start` or `python agent.py`) with clear README setup instructions; no manual config beyond setting an API key.
- Persistent memory across sessions: session 2 must demonstrably use facts learned in session 1, evidenced by committed terminal logs (session1.txt, session2.txt).
- At least 3 tools implemented with correct LLM tool-calling protocol (function/tool schema definitions); tools must be invoked by the model, not hard-coded by control flow.
- A verification layer that runs a deterministic check after every tool call and performs explicit recovery (retry, fallback, or logged error) on failure — not silent continuation.
- A DESIGN.md (<400 words) covering: tool design rationale, memory schema decisions, and one specific failure mode the verification layer addresses.

## Evaluation Criteria / 评判标准

- Agent architecture quality: Are tools well-scoped with clear, minimal schemas? Is memory structured (not just a raw chat log dump)? Does the design show judgment about what to persist vs. discard?
- Verification & error recovery: Is the verification layer deterministic and meaningful (not just a try/catch)? Does it actually handle a real failure mode rather than a trivial one?
- Cross-session memory effectiveness: Does session 2 genuinely use session 1 data in a way that improves the response — not just echoing stored text, but applying it contextually?
- Code quality under time pressure: Is the code readable, reasonably modular, and runnable without debugging? Are edge cases acknowledged even if not fully handled?
- DESIGN.md clarity: Does the candidate articulate *why* they made specific design choices (tool granularity, memory schema, verification strategy), not just *what* they built?

## Tech Hints / 技术提示

- TypeScript (recommended, given role stack) or Python
- OpenAI function calling / Anthropic tool use API for tool invocation
- SQLite (via better-sqlite3 or sqlite3) or JSON file for persistent memory store
- Zod (TS) or Pydantic (Python) for tool output schema validation in the verification layer
- Optional: LangChain, LlamaIndex, or a minimal custom agent loop — your choice signals architectural judgment

## Rules / 规则

- **Time limit / 时间限制**: 60 minutes (2026-05-22 07:43 UTC)
- **AI tools required / 必须使用 AI 工具**: Claude Code, Cursor, Copilot, etc. This challenge is designed to be impossible without AI tools — use them.
- **AI session logs are MANDATORY / AI 会话记录为必交项**: Your AI interaction history (`.claude/`, `.cursor/`, `.codex/`, `.windsurf/`, or `ai-session/`) is a core evaluation deliverable. Do NOT delete or `.gitignore` these directories. **Submissions without AI session logs will receive a significant scoring penalty.** / 不提交 AI 会话记录将严重扣分。
- **Multiple pushes OK / 可以多次 push**: We evaluate your last push before the deadline
- **Language / 语言**: Any programming language, any framework

## Getting Started / 开始

1. Read this CHALLENGE.md carefully
2. Use Claude Code (or Cursor / Codex / Windsurf) to build the project
3. `git push` your code (multiple pushes OK)
4. Keep `.claude/` (or `.cursor/` / `.codex/` / `.windsurf/`) committed — your AI session is the primary evidence we evaluate

Good luck! / 祝你好运！
