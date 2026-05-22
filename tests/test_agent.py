import os
import tempfile
import unittest
from pathlib import Path

import agent


class AgentTests(unittest.TestCase):
    def test_build_turn_memory_hint_for_persona_update(self) -> None:
        hint = agent.build_turn_memory_hint("你现在不是猫娘了，是狗娘，每句话结尾都加个汪")
        self.assertIsNotNone(hint)
        self.assertIn("remember_fact", hint)
        self.assertIn("persona.character", hint)

    def test_build_turn_memory_hint_for_memory_question(self) -> None:
        hint = agent.build_turn_memory_hint("你还记得我最喜欢的歌手是谁吗")
        self.assertIsNotNone(hint)
        self.assertIn("recall_context", hint)

    def test_startup_persona_memories_are_preloaded_but_regular_preferences_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            memory = agent.MemoryStore(db_path)
            memory.remember_fact(
                category="persona",
                key="character",
                value="猫娘，每句话结尾加喵",
                confidence=1.0,
                session_id="session-a",
            )
            memory.remember_fact(
                category="preferences",
                key="favorite_singer",
                value="Taylor Swift",
                confidence=1.0,
                session_id="session-a",
            )
            app = agent.Agent(memory, agent.ScriptedModelClient(), "session-b")
            base_messages = app._base_messages()
            memory.close()
            self.assertEqual(len(base_messages), 1)
            self.assertEqual(base_messages[0]["role"], "system")
            self.assertIn("猫娘，每句话结尾加喵", base_messages[0]["content"])
            self.assertNotIn("Taylor Swift", base_messages[0]["content"])

    def test_remember_fact_normalizes_ai_persona_to_startup_persona_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = agent.MemoryStore(Path(tmpdir) / "memory.db")
            tools = agent.ToolExecutor(memory, "session-test")
            result = tools.execute(
                agent.ToolCall(
                    id="1",
                    name="remember_fact",
                    arguments={
                        "category": "preferences",
                        "key": "ai_persona",
                        "value": "猫娘性格，每句话结尾加喵，称用户为主人",
                        "confidence": 0.95,
                    },
                )
            )
            startup_memories = memory.startup_memories()
            memory.close()
            self.assertEqual(result["payload"]["fact"]["category"], "persona")
            self.assertEqual(result["payload"]["fact"]["key"], "character")
            self.assertTrue(startup_memories)
            self.assertEqual(startup_memories[0]["category"], "persona")
            self.assertEqual(startup_memories[0]["key"], "character")

    def test_agent_handles_provider_timeout_gracefully(self) -> None:
        class TimeoutModelClient:
            def complete(self, messages, tools):
                raise TimeoutError("The read operation timed out")

        with tempfile.TemporaryDirectory() as tmpdir:
            memory = agent.MemoryStore(Path(tmpdir) / "memory.db")
            app = agent.Agent(memory, TimeoutModelClient(), "session-timeout")
            reply = app.run_turn("What do you remember about me?")
            memory.close()
            self.assertIn("timed out", reply.lower())
            self.assertIn("MIAO_HTTP_TIMEOUT", reply)

    def test_load_secret_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "minimax.key"
            secret_path.write_text("secret-value\n", encoding="utf-8")
            original_direct = os.environ.get("MINIMAX_API_KEY")
            original_file = os.environ.get("MINIMAX_API_KEY_FILE")
            try:
                os.environ.pop("MINIMAX_API_KEY", None)
                os.environ["MINIMAX_API_KEY_FILE"] = str(secret_path)
                self.assertEqual(agent.load_secret("MINIMAX_API_KEY", "MINIMAX_API_KEY_FILE"), "secret-value")
            finally:
                if original_direct is None:
                    os.environ.pop("MINIMAX_API_KEY", None)
                else:
                    os.environ["MINIMAX_API_KEY"] = original_direct
                if original_file is None:
                    os.environ.pop("MINIMAX_API_KEY_FILE", None)
                else:
                    os.environ["MINIMAX_API_KEY_FILE"] = original_file

    def test_strip_thinking_tags_hides_internal_reasoning(self) -> None:
        raw = "<think>internal reasoning</think>\nFinal answer"
        self.assertEqual(agent.strip_thinking_tags(raw), "Final answer")

    def test_memory_persists_across_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            memory1 = agent.MemoryStore(db_path)
            agent1 = agent.Agent(memory1, agent.ScriptedModelClient(), "session-1")
            reply1 = agent1.run_turn("Please remember that my favorite color is green and that I am vegetarian.")
            self.assertIn("favorite_color", reply1)
            agent1.finalize_session()
            memory1.close()

            memory2 = agent.MemoryStore(db_path)
            recalled = memory2.recall_context("lunch vegetarian favorite color", limit=5)
            memory2.close()
            values = {item["value"] for item in recalled}
            self.assertIn("green", values)
            self.assertIn("vegetarian", values)

    def test_recall_context_matches_dietary_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            memory = agent.MemoryStore(db_path)
            memory.remember_fact(
                category="preferences",
                key="favorite_color",
                value="green",
                confidence=1.0,
                session_id="session-a",
            )
            memory.remember_fact(
                category="diet",
                key="diet",
                value="vegetarian",
                confidence=1.0,
                session_id="session-a",
            )
            recalled = memory.recall_context(
                "user preferences, personal information, dietary restrictions, likes, dislikes, past conversations",
                limit=5,
            )
            memory.close()
            values = {item["value"] for item in recalled}
            self.assertIn("green", values)
            self.assertIn("vegetarian", values)
            diet_rows = [item for item in recalled if item["value"] == "vegetarian"]
            self.assertTrue(diet_rows)
            self.assertGreaterEqual(diet_rows[0]["relevance_score"], 1)

    def test_recall_context_matches_chinese_persona_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            memory = agent.MemoryStore(db_path)
            memory.remember_fact(
                category="persona",
                key="character",
                value="猫娘，每句话结尾加喵",
                confidence=1.0,
                session_id="session-a",
            )
            recalled = memory.recall_context("我上一轮对话的时候跟你说过你是猫娘你还记得吗", limit=5)
            memory.close()
            self.assertTrue(recalled)
            self.assertEqual(recalled[0]["category"], "persona")
            self.assertEqual(recalled[0]["value"], "猫娘，每句话结尾加喵")
            self.assertGreaterEqual(recalled[0]["relevance_score"], 1)

    def test_calculate_recovery_normalizes_expression(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = agent.MemoryStore(Path(tmpdir) / "memory.db")
            tools = agent.ToolExecutor(memory, "session-test")
            result = tools.execute(
                agent.ToolCall(id="1", name="calculate", arguments={"expression": "12 x 8 + 4"})
            )
            memory.close()
            self.assertEqual(result["verification_status"], "recovered")
            self.assertEqual(result["payload"]["result"], 100.0)

    def test_choose_provider_minimax_uses_official_defaults(self) -> None:
        original_api_key = os.environ.get("MINIMAX_API_KEY")
        original_base_url = os.environ.get("MINIMAX_BASE_URL")
        original_model = os.environ.get("MINIMAX_MODEL")
        original_timeout = os.environ.get("MIAO_HTTP_TIMEOUT")
        original_retries = os.environ.get("MIAO_API_RETRIES")
        try:
            os.environ["MINIMAX_API_KEY"] = "test-key"
            os.environ.pop("MINIMAX_BASE_URL", None)
            os.environ.pop("MINIMAX_MODEL", None)
            os.environ.pop("MIAO_HTTP_TIMEOUT", None)
            os.environ.pop("MIAO_API_RETRIES", None)
            client = agent.choose_provider("minimax")
            self.assertEqual(client.base_url, "https://api.minimax.io/v1")
            self.assertEqual(client.model, "MiniMax-M2.7")
            self.assertEqual(client.extra_body, {"reasoning_split": False})
            self.assertEqual(client.timeout_seconds, 120.0)
            self.assertEqual(client.max_retries, 2)
        finally:
            if original_api_key is None:
                os.environ.pop("MINIMAX_API_KEY", None)
            else:
                os.environ["MINIMAX_API_KEY"] = original_api_key
            if original_base_url is None:
                os.environ.pop("MINIMAX_BASE_URL", None)
            else:
                os.environ["MINIMAX_BASE_URL"] = original_base_url
            if original_model is None:
                os.environ.pop("MINIMAX_MODEL", None)
            else:
                os.environ["MINIMAX_MODEL"] = original_model
            if original_timeout is None:
                os.environ.pop("MIAO_HTTP_TIMEOUT", None)
            else:
                os.environ["MIAO_HTTP_TIMEOUT"] = original_timeout
            if original_retries is None:
                os.environ.pop("MIAO_API_RETRIES", None)
            else:
                os.environ["MIAO_API_RETRIES"] = original_retries


if __name__ == "__main__":
    unittest.main()
