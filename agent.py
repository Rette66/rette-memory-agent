import argparse
import ast
import json
import math
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = """You are MiAO, a personal AI agent.
Use tools when they would improve correctness or memory.
Standing assistant identity or speaking-style settings from previous sessions may be preloaded at startup.
Treat those startup settings as active unless the user changes them in the current session.
For other user memories, use recall_context when the user asks about prior facts, preferences, or earlier instructions.
Always prefer:
1. remember_fact for stable user preferences or facts,
2. recall_context before answering questions that depend on prior sessions,
3. calculate for arithmetic instead of mental math.
Before answering questions about what you remember, prior instructions, the assistant's role, persona, identity, or speaking style, check memory first unless the startup context already fully answers it.
When recall_context returns memories, explicitly use all memories relevant to the user's request.
For food or restaurant suggestions, prioritize diet-related memories over stylistic preferences like colors.
When a tool fails, explain what happened and continue safely.
Keep responses concise and practical.
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def strip_thinking_tags(content: str) -> str:
    stripped = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return stripped or content.strip()


def load_secret(env_name: str, file_env_name: str) -> str | None:
    direct = os.environ.get(env_name)
    if direct:
        return direct
    file_path = os.environ.get(file_env_name)
    if not file_path:
        return None
    path = Path(file_path).expanduser()
    if not path.exists():
        raise RuntimeError(f"{file_env_name} points to a missing file: {path}")
    return path.read_text(encoding="utf-8").strip() or None


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number, got: {raw}") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0, got: {raw}")
    return value


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got: {raw}") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be >= 1, got: {raw}")
    return value


TOKEN_ALIASES = {
    "preferences": "preference",
    "likes": "preference",
    "dislikes": "preference",
    "favorite": "preference",
    "favourite": "preference",
    "dietary": "diet",
    "restriction": "diet",
    "restrictions": "diet",
    "meal": "diet",
    "meals": "diet",
    "lunch": "diet",
    "dinner": "diet",
    "breakfast": "diet",
    "vegetarian": "diet",
    "vegan": "diet",
}

PHRASE_ALIASES = {
    "persona": {"persona"},
    "character": {"persona"},
    "role": {"persona"},
    "identity": {"persona"},
    "style": {"style"},
    "tone": {"style"},
    "catgirl": {"persona", "catgirl"},
    "meow": {"style", "meow"},
    "favorite color": {"preference", "color"},
    "favorite singer": {"preference", "music"},
    "favorite song": {"preference", "music"},
    "food": {"diet"},
    "restaurant": {"diet"},
    "launch": {"diet"},
    "角色": {"persona"},
    "角色设置": {"persona", "style"},
    "角色设定": {"persona", "style"},
    "人设": {"persona"},
    "设定": {"persona"},
    "身份": {"persona"},
    "猫娘": {"persona", "catgirl"},
    "喵": {"style", "meow"},
    "说话": {"style"},
    "语气": {"style"},
    "口癖": {"style"},
    "风格": {"style"},
    "结尾": {"style", "suffix"},
    "上一轮": {"history"},
    "上次": {"history"},
    "之前": {"history"},
    "记得": {"memory"},
    "素食": {"diet"},
    "素食主义": {"diet"},
    "午饭": {"diet"},
    "午餐": {"diet"},
    "晚餐": {"diet"},
    "早餐": {"diet"},
    "吃什么": {"diet"},
    "歌手": {"music"},
    "颜色": {"color"},
    "喜欢": {"preference"},
}

GENERIC_MEMORY_TOKENS = {
    "user",
    "personal",
    "information",
    "past",
    "conversation",
    "conversations",
    "history",
    "context",
    "remember",
    "memory",
    "stored",
    "about",
    "me",
}

STARTUP_MEMORY_CATEGORIES = {"persona", "style", "tone", "assistant_identity"}
STARTUP_MEMORY_KEYS = {"character", "persona", "role", "identity", "style", "speaking_style", "tone", "suffix", "ai_persona"}

MEMORY_WRITE_HINT_PATTERNS = [
    r"记住",
    r"以后",
    r"从现在开始",
    r"改成",
    r"不是.+是",
    r"我最喜欢",
    r"我喜欢",
    r"我不喜欢",
    r"我只吃",
    r"我不吃",
    r"设定",
    r"角色",
    r"口癖",
    r"称呼",
    r"猫娘",
    r"狗娘",
    r"favorite",
    r"prefer",
    r"from now on",
    r"call me",
]

MEMORY_READ_HINT_PATTERNS = [
    r"你记得",
    r"你还记得",
    r"你记不记得",
    r"你有什么设定",
    r"你的设定",
    r"你是什么角色",
    r"what do you remember",
    r"do you remember",
    r"what is my",
    r"who is my favorite",
    r"上一轮",
    r"上次",
    r"之前",
]


def canonicalize_token(token: str) -> str:
    token = token.lower().strip("_")
    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        token = token[:-1]
    return TOKEN_ALIASES.get(token, token)


def memory_tokens(text: str) -> set[str]:
    lowered = text.lower()
    raw_tokens = re.findall(r"[a-z0-9_]+", lowered)
    expanded_tokens: set[str] = set()
    for token in raw_tokens:
        expanded_tokens.add(token)
        for part in token.split("_"):
            if part:
                expanded_tokens.add(part)
    normalized = {canonicalize_token(token) for token in expanded_tokens}
    phrase_tokens: set[str] = set()
    for phrase, aliases in PHRASE_ALIASES.items():
        if phrase in text or phrase in lowered:
            phrase_tokens.update(aliases)
    combined = normalized.union(phrase_tokens)
    return {token for token in combined if token and token not in GENERIC_MEMORY_TOKENS}


def normalize_fact_fields(category: str, key: str, value: str) -> tuple[str, str]:
    category = category.strip().lower() or "general"
    key = key.strip().lower()
    value_lower = value.lower()

    if category in {"preferences", "preference"}:
        category = "preference"

    if (
        key in {"ai_persona", "persona", "character", "role", "identity", "speaking_style", "style", "tone"}
        or any(marker in value_lower for marker in ["猫娘", "狗娘", "喵", "汪", "主人", "catgirl", "doggirl", "meow", "woof"])
    ):
        return "persona", "character"

    if key in {"favorite_colour", "favourite_color", "favourite_colour", "color", "colour"}:
        return "preference", "favorite_color"

    if key in {"favorite_singer", "favourite_singer", "favorite_artist", "singer"}:
        return "preference", "favorite_singer"

    if key in {"food_preference", "dietary_preference", "diet"}:
        return "diet", "food_preference"

    return category, key


def build_turn_memory_hint(user_text: str) -> str | None:
    hints: list[str] = []
    lowered = user_text.lower()

    if any(re.search(pattern, user_text, flags=re.IGNORECASE) for pattern in MEMORY_WRITE_HINT_PATTERNS):
        hints.append(
            "This user message likely contains a durable memory update. "
            "If so, call remember_fact before replying."
        )
        hints.append(
            "Use canonical memory keys when possible: "
            "persona.character for assistant role/style, "
            "preference.favorite_color for favorite color, "
            "preference.favorite_singer for favorite singer, "
            "diet.food_preference for food habits."
        )

    if any(re.search(pattern, user_text, flags=re.IGNORECASE) for pattern in MEMORY_READ_HINT_PATTERNS):
        hints.append(
            "This user message likely depends on prior memory. "
            "If the startup persona does not fully answer it, call recall_context before replying."
        )

    if "persona" in lowered or "style" in lowered or "role" in lowered or any(
        marker in user_text for marker in ["角色", "设定", "身份", "口癖", "猫娘", "狗娘", "喵", "汪"]
    ):
        hints.append(
            "Persona or speaking-style instructions should be treated as durable assistant settings."
        )

    if not hints:
        return None
    return "\n".join(hints)


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source_session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(category, key, value)
            );

            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def remember_fact(
        self,
        *,
        category: str,
        key: str,
        value: str,
        confidence: float,
        session_id: str,
    ) -> dict[str, Any]:
        created_at = utc_now()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO facts (category, key, value, confidence, source_session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, key, value) DO UPDATE SET
                confidence=excluded.confidence,
                source_session_id=excluded.source_session_id
            """,
            (category, key, value, confidence, session_id, created_at),
        )
        self.conn.commit()
        row = cur.execute(
            """
            SELECT id, category, key, value, confidence, source_session_id, created_at
            FROM facts
            WHERE category = ? AND key = ? AND value = ?
            """,
            (category, key, value),
        ).fetchone()
        return dict(row)

    def _latest_rows(self) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT id, category, key, value, confidence, source_session_id, created_at
            FROM facts
            ORDER BY created_at DESC
            """
        ).fetchall()
        latest_rows: list[sqlite3.Row] = []
        seen_keys: set[tuple[str, str]] = set()
        for row in rows:
            dedupe_key = (row["category"], row["key"])
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            latest_rows.append(row)
        return latest_rows

    def startup_memories(self, limit: int = 8) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for row in self._latest_rows():
            category = row["category"].strip().lower()
            key = row["key"].strip().lower()
            if category in STARTUP_MEMORY_CATEGORIES or key in STARTUP_MEMORY_KEYS:
                selected.append(dict(row))
            if len(selected) >= limit:
                break
        return selected

    def recall_context(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = memory_tokens(query)
        rows = self._latest_rows()
        scored: list[tuple[int, str, sqlite3.Row]] = []
        for row in rows:
            haystack_tokens = memory_tokens(" ".join([row["category"], row["key"], row["value"]]))
            matched_tokens = sorted(tokens.intersection(haystack_tokens))
            score = len(matched_tokens)
            scored.append((score, ",".join(matched_tokens), row))
        scored.sort(key=lambda item: (item[0], item[2]["created_at"]), reverse=True)
        results: list[dict[str, Any]] = []
        for score, matched_token_text, row in scored[:limit]:
            item = dict(row)
            item["relevance_score"] = score
            item["matched_terms"] = [token for token in matched_token_text.split(",") if token]
            results.append(item)
        return results

    def recent_facts(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, category, key, value, confidence, source_session_id, created_at
            FROM facts
            WHERE source_session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def append_session_summary(self, session_id: str, summary: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO session_summaries (session_id, summary_json, created_at)
            VALUES (?, ?, ?)
            """,
            (session_id, json.dumps(summary, ensure_ascii=False, indent=2), utc_now()),
        )
        self.conn.commit()

    def log_tool_event(
        self,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        verification_status: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO tool_events (session_id, tool_name, arguments_json, result_json, verification_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                verification_status,
                utc_now(),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def safe_eval(expression: str) -> float:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Load,
        ast.FloorDiv,
    )
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"disallowed expression node: {type(node).__name__}")
    result = eval(compile(tree, "<calculate>", "eval"), {"__builtins__": {}}, {})
    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise ValueError("expression did not produce a finite number")
    return float(result)


def normalize_expression(expression: str) -> str:
    cleaned = expression.strip().lower()
    replacements = {
        "x": "*",
        "×": "*",
        "plus": "+",
        "minus": "-",
        "times": "*",
        "divided by": "/",
        "=": "",
        "?": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    allowed_chars = set("0123456789+-*/(). %")
    cleaned = "".join(ch for ch in cleaned if ch in allowed_chars)
    return " ".join(cleaned.split())


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


class ToolExecutor:
    def __init__(self, memory: MemoryStore, session_id: str) -> None:
        self.memory = memory
        self.session_id = session_id

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "remember_fact",
                    "description": "Store a durable user fact or preference for future sessions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["category", "key", "value"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recall_context",
                    "description": (
                        "Retrieve relevant stored memories for the current user request. "
                        "Use this for prior facts, preferences, previous instructions, or non-startup memories."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Safely evaluate an arithmetic expression.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                        },
                        "required": ["expression"],
                    },
                },
            },
        ]

    def execute(self, call: ToolCall) -> dict[str, Any]:
        name = call.name
        args = dict(call.arguments)
        verification_status = "passed"
        if name == "remember_fact":
            result, verification_status = self._remember_fact(args)
        elif name == "recall_context":
            result, verification_status = self._recall_context(args)
        elif name == "calculate":
            result, verification_status = self._calculate(args)
        else:
            result = {"status": "error", "error": f"unknown tool: {name}"}
            verification_status = "failed"

        self.memory.log_tool_event(
            session_id=self.session_id,
            tool_name=name,
            arguments=args,
            result=result,
            verification_status=verification_status,
        )
        return {
            "tool_name": name,
            "verification_status": verification_status,
            "payload": result,
        }

    def _remember_fact(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        category = str(args.get("category", "")).strip().lower() or "general"
        key = str(args.get("key", "")).strip().lower()
        value = str(args.get("value", "")).strip()
        confidence = float(args.get("confidence", 1.0) or 1.0)

        if not key or not value:
            repaired = {
                "status": "error",
                "error": "verification failed: key and value must be non-empty strings",
            }
            return repaired, "failed"

        category, key = normalize_fact_fields(category, key, value)
        confidence = min(max(confidence, 0.0), 1.0)
        row = self.memory.remember_fact(
            category=category,
            key=key,
            value=value,
            confidence=confidence,
            session_id=self.session_id,
        )
        verified = row["key"] == key and row["value"] == value
        status = "passed" if verified else "failed"
        return {"status": "stored", "fact": row}, status

    def _recall_context(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 5) or 5)
        if limit <= 0 or limit > 10:
            limit = 5
            verification_status = "recovered"
        else:
            verification_status = "passed"
        memories = self.memory.recall_context(query, limit=limit)
        return {
            "status": "ok",
            "query": query,
            "count": len(memories),
            "memories": memories,
        }, verification_status

    def _calculate(self, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        expression = str(args.get("expression", "")).strip()
        try:
            result = safe_eval(expression)
            return {"status": "ok", "expression": expression, "result": result}, "passed"
        except Exception as first_error:
            normalized = normalize_expression(expression)
            try:
                result = safe_eval(normalized)
                return {
                    "status": "ok",
                    "expression": expression,
                    "normalized_expression": normalized,
                    "result": result,
                    "recovery": f"recovered from {type(first_error).__name__}",
                }, "recovered"
            except Exception as second_error:
                return {
                    "status": "error",
                    "expression": expression,
                    "normalized_expression": normalized,
                    "error": f"{type(second_error).__name__}: {second_error}",
                }, "failed"


class OpenAICompatibleChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        provider_label: str,
        extra_body: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.5,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.provider_label = provider_label
        self.extra_body = extra_body or {}
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def _timeout_message(self) -> str:
        timeout_display = f"{self.timeout_seconds:g}"
        return (
            f"{self.provider_label} API timed out after {timeout_display}s. "
            "Try again, or increase MIAO_HTTP_TIMEOUT (for example 180)."
        )

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        payload.update(self.extra_body)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        last_timeout: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"{self.provider_label} API error: {exc.code} {detail}") from exc
            except (TimeoutError, socket.timeout) as exc:
                last_timeout = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                raise RuntimeError(self._timeout_message()) from exc
            except urllib.error.URLError as exc:
                reason_text = str(exc.reason).lower()
                if "timed out" in reason_text:
                    last_timeout = exc
                    if attempt < self.max_retries:
                        time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    raise RuntimeError(self._timeout_message()) from exc
                raise RuntimeError(f"{self.provider_label} API connection error: {exc.reason}") from exc
        else:
            raise RuntimeError(self._timeout_message()) from last_timeout

        message = payload["choices"][0]["message"]
        tool_calls = []
        for item in message.get("tool_calls", []) or []:
            tool_calls.append(
                ToolCall(
                    id=item["id"],
                    name=item["function"]["name"],
                    arguments=json.loads(item["function"]["arguments"]),
                )
            )
        return {
            "content": message.get("content", "") or "",
            "tool_calls": tool_calls,
        }


class ScriptedModelClient:
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        last_message = messages[-1]
        if last_message["role"] == "user":
            user_text = last_message["content"].lower()
            tool_calls: list[ToolCall] = []

            if "favorite color" in user_text and "green" in user_text:
                tool_calls.append(
                    ToolCall(
                        id=str(uuid.uuid4()),
                        name="remember_fact",
                        arguments={
                            "category": "preference",
                            "key": "favorite_color",
                            "value": "green",
                            "confidence": 0.98,
                        },
                    )
                )

            if "vegetarian" in user_text:
                tool_calls.append(
                    ToolCall(
                        id=str(uuid.uuid4()),
                        name="remember_fact",
                        arguments={
                            "category": "diet",
                            "key": "dietary_preference",
                            "value": "vegetarian",
                            "confidence": 0.96,
                        },
                    )
                )

            if "remember" in user_text or "last time" in user_text or "lunch" in user_text:
                tool_calls.append(
                    ToolCall(
                        id=str(uuid.uuid4()),
                        name="recall_context",
                        arguments={"query": user_text, "limit": 4},
                    )
                )

            if any(token in user_text for token in ["calculate", "what is", "12 x 8", "math"]):
                expression = "12 x 8 + 4" if "12 x 8" in user_text else user_text
                tool_calls.append(
                    ToolCall(
                        id=str(uuid.uuid4()),
                        name="calculate",
                        arguments={"expression": expression},
                    )
                )

            if tool_calls:
                return {"content": "", "tool_calls": tool_calls}

            return {
                "content": "I can help with memory and arithmetic. Tell me a preference to remember or ask a question that depends on prior sessions.",
                "tool_calls": [],
            }

        if last_message["role"] == "tool":
            tool_payloads = []
            idx = len(messages) - 1
            while idx >= 0 and messages[idx]["role"] == "tool":
                tool_payloads.append(json.loads(messages[idx]["content"]))
                idx -= 1
            tool_payloads.reverse()
            lines = []
            memories: list[dict[str, Any]] = []
            calc_result: float | None = None
            recovered_math = False
            for payload in tool_payloads:
                tool_name = payload["tool_name"]
                result = payload["payload"]
                if tool_name == "remember_fact" and result["status"] == "stored":
                    fact = result["fact"]
                    lines.append(f"I stored that your {fact['key']} is {fact['value']}.")
                elif tool_name == "recall_context":
                    memories = result["memories"]
                elif tool_name == "calculate" and result["status"] == "ok":
                    calc_result = result["result"]
                    recovered_math = payload["verification_status"] == "recovered"
            if memories:
                memory_text = "; ".join(f"{item['key']}={item['value']}" for item in memories)
                lines.append(f"From memory I found: {memory_text}.")
                if any(item["value"] == "vegetarian" for item in memories):
                    lines.append("A vegetarian lunch like a tofu bowl or veggie sandwich fits you better.")
                if any(item["value"] == "green" for item in memories):
                    lines.append("I also remember green is your favorite color, so I would pick the green-themed cafe if there are two similar options.")
            if calc_result is not None:
                recovery_note = " after normalizing the expression" if recovered_math else ""
                lines.append(f"The math result is {calc_result:g}{recovery_note}.")
            if not lines:
                lines.append("I checked the tools and didn't get a useful result.")
            return {"content": " ".join(lines), "tool_calls": []}

        return {"content": "How can I help?", "tool_calls": []}


class Agent:
    def __init__(self, memory: MemoryStore, model_client: Any, session_id: str) -> None:
        self.memory = memory
        self.model_client = model_client
        self.session_id = session_id
        self.tool_executor = ToolExecutor(memory, session_id)
        self.turn_log: list[dict[str, Any]] = []

    def _base_messages(self) -> list[dict[str, Any]]:
        startup_memories = self.memory.startup_memories()
        system_content = SYSTEM_PROMPT
        if startup_memories:
            lines = [
                "Startup memory loaded from previous sessions.",
                "Treat the following assistant identity or speaking-style settings as active unless the user changes them in this session:",
            ]
            for item in startup_memories:
                lines.append(f"- {item['category']}.{item['key']} = {item['value']}")
            system_content = f"{SYSTEM_PROMPT.rstrip()}\n\n" + "\n".join(lines)
        return [{"role": "system", "content": system_content}]

    def _messages_for_turn(self, user_text: str) -> list[dict[str, Any]]:
        history_without_current_user = self.turn_log[:-1]
        current_user_message = self.turn_log[-1]
        messages = self._base_messages() + history_without_current_user
        turn_hint = build_turn_memory_hint(user_text)
        if turn_hint:
            messages.append({"role": "system", "content": turn_hint})
        messages.append(current_user_message)
        return messages

    def _provider_error_message(self, exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        if "timed out" in message.lower():
            return (
                "The model request timed out, so I could not finish this turn. "
                "Please try again. If it happens repeatedly, increase `MIAO_HTTP_TIMEOUT` "
                "(for example to `180`) and rerun the command."
            )
        return f"I hit a provider error and stopped this turn safely: {message}"

    def run_turn(self, user_text: str) -> str:
        self.turn_log.append({"role": "user", "content": user_text})
        messages = self._messages_for_turn(user_text)
        for _ in range(8):
            try:
                result = self.model_client.complete(messages, self.tool_executor.specs())
            except Exception as exc:
                assistant_text = self._provider_error_message(exc)
                self.turn_log.append({"role": "assistant", "content": assistant_text})
                return assistant_text
            tool_calls: list[ToolCall] = result["tool_calls"]
            if tool_calls:
                assistant_message = {
                    "role": "assistant",
                    "content": result["content"],
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        for call in tool_calls
                    ],
                }
                self.turn_log.append(assistant_message)
                messages.append(assistant_message)
                for call in tool_calls:
                    tool_result = self.tool_executor.execute(call)
                    print(
                        f"[tool] {call.name} args={json.dumps(call.arguments, ensure_ascii=False)} "
                        f"verification={tool_result['verification_status']}"
                    )
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                    self.turn_log.append(tool_message)
                    messages.append(tool_message)
                continue

            raw_assistant_text = result["content"].strip()
            assistant_text = strip_thinking_tags(raw_assistant_text) or "I don't have a confident answer yet."
            self.turn_log.append({"role": "assistant", "content": raw_assistant_text or assistant_text})
            return assistant_text
        fallback = "I hit the tool loop limit, so I'm stopping safely."
        self.turn_log.append({"role": "assistant", "content": fallback})
        return fallback

    def finalize_session(self) -> dict[str, Any]:
        recent_facts = self.memory.recent_facts(self.session_id)
        user_turns = [item["content"] for item in self.turn_log if item["role"] == "user"]
        assistant_turns = [item["content"] for item in self.turn_log if item["role"] == "assistant" and item.get("content")]
        summary = {
            "session_id": self.session_id,
            "ended_at": utc_now(),
            "facts_learned": [
                {
                    "category": item["category"],
                    "key": item["key"],
                    "value": item["value"],
                    "confidence": item["confidence"],
                }
                for item in recent_facts
            ],
            "user_topics": user_turns,
            "assistant_highlights": assistant_turns[-3:],
        }
        self.memory.append_session_summary(self.session_id, summary)
        return summary


def choose_provider(provider: str) -> Any:
    timeout_seconds = env_float("MIAO_HTTP_TIMEOUT", 120.0)
    max_retries = env_int("MIAO_API_RETRIES", 2)
    retry_backoff_seconds = env_float("MIAO_RETRY_BACKOFF_SECONDS", 1.5)
    if provider == "scripted":
        return ScriptedModelClient()
    if provider == "openai":
        api_key = load_secret("OPENAI_API_KEY", "OPENAI_API_KEY_FILE")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY or OPENAI_API_KEY_FILE is required when provider=openai")
        model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatibleChatClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider_label="OpenAI",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    if provider == "minimax":
        api_key = (
            load_secret("MINIMAX_API_KEY", "MINIMAX_API_KEY_FILE")
            or load_secret("OPENAI_API_KEY", "OPENAI_API_KEY_FILE")
        )
        if not api_key:
            raise RuntimeError(
                "MINIMAX_API_KEY or MINIMAX_API_KEY_FILE is required when provider=minimax "
                "(OPENAI_API_KEY / OPENAI_API_KEY_FILE also work if you already reuse those names)"
            )
        model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7")
        base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
        return OpenAICompatibleChatClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider_label="MiniMax",
            extra_body={"reasoning_split": False},
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    raise ValueError(f"unsupported provider: {provider}")


def interactive_session(agent: Agent, scripted_inputs: list[str] | None = None) -> None:
    print(f"MiAO Agent session: {agent.session_id}")
    print("Type 'exit' to finish.\n")
    inputs = list(scripted_inputs or [])
    while True:
        if inputs:
            user_text = inputs.pop(0)
            print(f"You> {user_text}")
        else:
            try:
                user_text = input("You> ").strip()
            except EOFError:
                user_text = "exit"
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break
        reply = agent.run_turn(user_text)
        print(f"Agent> {reply}\n")
    summary = agent.finalize_session()
    print("Session summary saved:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MiAO personal AI agent CLI")
    parser.add_argument("--provider", default=os.environ.get("MIAO_PROVIDER", "openai"))
    parser.add_argument("--db", default="data/memory.db")
    parser.add_argument("--script-file", help="Optional file with one user message per line.")
    parser.add_argument("--reset-memory", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    if args.reset_memory and db_path.exists():
        db_path.unlink()
    try:
        model_client = choose_provider(args.provider)
    except Exception as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1

    memory = MemoryStore(db_path)
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(uuid.uuid4())[:8]
    agent = Agent(memory=memory, model_client=model_client, session_id=session_id)

    scripted_inputs = None
    if args.script_file:
        scripted_inputs = [
            line.strip()
            for line in Path(args.script_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    try:
        interactive_session(agent, scripted_inputs=scripted_inputs)
    finally:
        memory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
