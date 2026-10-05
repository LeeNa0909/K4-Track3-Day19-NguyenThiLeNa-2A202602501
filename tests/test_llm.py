"""Offline checks for OpenRouter selection and request routing."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.llm import MeteredLLM, pick_provider


class TestOpenRouter(unittest.TestCase):
    def test_openrouter_wins_when_both_keys_are_present(self):
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "router-test-key",
            "OPENAI_API_KEY": "openai-test-key",
        }, clear=True):
            self.assertEqual(pick_provider("LLM_PROVIDER", False), "openrouter")
            self.assertEqual(pick_provider("EMBEDDING_PROVIDER", True), "openrouter")

    def test_explicit_provider_still_takes_precedence(self):
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "router-test-key",
            "OPENAI_API_KEY": "openai-test-key",
            "LLM_PROVIDER": "openai",
            "EMBEDDING_PROVIDER": "openai",
        }, clear=True):
            self.assertEqual(pick_provider("LLM_PROVIDER", False), "openai")
            self.assertEqual(pick_provider("EMBEDDING_PROVIDER", True), "openai")

    def test_missing_router_key_does_not_use_another_provider_silently(self):
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "openai-test-key",
            "LLM_PROVIDER": "openrouter",
            "EMBEDDING_PROVIDER": "openrouter",
        }, clear=True):
            for env_var, need_embeddings in [("LLM_PROVIDER", False), ("EMBEDDING_PROVIDER", True)]:
                with self.subTest(env_var=env_var):
                    with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                        pick_provider(env_var, need_embeddings)

    def test_chat_and_embedding_use_router_key_and_endpoint(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
        client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])],
            usage=SimpleNamespace(prompt_tokens=3),
        )
        constructor = Mock(return_value=client)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "router-test-key"}, clear=True):
            with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=constructor)}):
                llm = MeteredLLM()
                self.assertEqual(llm.chat("Return JSON", json_mode=True), '{"ok": true}')
                self.assertEqual(llm.embed("hello"), [0.1, 0.2])

        constructor.assert_called_once_with(
            api_key="router-test-key", base_url="https://openrouter.ai/api/v1",
        )
        client.chat.completions.create.assert_called_once_with(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": "Return JSON"}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        client.embeddings.create.assert_called_once_with(
            model="openai/text-embedding-3-small", input="hello",
        )
        self.assertEqual(llm.usage.calls, 2)
        self.assertEqual(llm.usage.input_tokens, 13)
        self.assertEqual(llm.usage.output_tokens, 5)
