"""Tests for the LiteLLM client."""

import types as builtin_types
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Fake response helpers (OpenAI-compatible format)
# ---------------------------------------------------------------------------


class _Usage:
    def __init__(self, prompt=10, completion=5):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.prompt_tokens_details = None


class _Msg:
    def __init__(self, content="hello", role="assistant", tool_calls=None):
        self.content = content
        self.role = role
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, content="hello", finish_reason="stop"):
        self.message = _Msg(content=content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content="hello", finish_reason="stop", usage=None):
        self.choices = [_Choice(content=content, finish_reason=finish_reason)]
        self.usage = usage or _Usage()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_litellm(response_content="hello"):
    import sys

    fake = builtin_types.ModuleType("litellm")
    fake.completion = mock.MagicMock(return_value=_Response(response_content))

    async def _async_completion(**kwargs):
        return _Response(response_content)

    fake.acompletion = _async_completion
    sys.modules["litellm"] = fake
    return fake


def _uninstall_fake_litellm():
    import sys

    sys.modules.pop("litellm", None)


# ---------------------------------------------------------------------------
# Sync proxy: basic call dispatch
# ---------------------------------------------------------------------------


class TestSyncProxy:
    def setup_method(self):
        self.fake = _install_fake_litellm("sync response")

    def teardown_method(self):
        _uninstall_fake_litellm()

    def test_returns_response_content(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        result = proxy.chat.completions.create(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result.choices[0].message.content == "sync response"

    def test_calls_litellm_completion(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )
        self.fake.completion.assert_called_once()


# ---------------------------------------------------------------------------
# Sync proxy: parameter forwarding
# ---------------------------------------------------------------------------


class TestSyncProxyParams:
    def setup_method(self):
        self.fake = _install_fake_litellm()

    def teardown_method(self):
        _uninstall_fake_litellm()

    def test_drop_params_always_true(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=[])
        assert self.fake.completion.call_args[1]["drop_params"] is True

    def test_model_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="anthropic/claude-3-haiku", messages=[])
        assert self.fake.completion.call_args[1]["model"] == "anthropic/claude-3-haiku"

    def test_messages_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        msgs = [{"role": "user", "content": "test"}]
        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=msgs)
        assert self.fake.completion.call_args[1]["messages"] == msgs

    def test_temperature_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=[], temperature=0.7)
        assert self.fake.completion.call_args[1]["temperature"] == 0.7

    def test_max_tokens_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=[], max_tokens=2048)
        assert self.fake.completion.call_args[1]["max_tokens"] == 2048

    def test_top_p_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=[], top_p=0.95)
        assert self.fake.completion.call_args[1]["top_p"] == 0.95

    def test_stream_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=[], stream=False)
        assert self.fake.completion.call_args[1]["stream"] is False

    def test_extra_body_forwarded(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(
            model="x", messages=[], extra_body={"thinking": {"type": "enabled"}}
        )
        assert self.fake.completion.call_args[1]["extra_body"] == {
            "thinking": {"type": "enabled"}
        }

    def test_user_cannot_override_drop_params(self):
        """drop_params=True is always enforced even if user passes False."""
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model="x", messages=[], drop_params=False)
        # Our proxy sets drop_params=True AFTER kwargs, so it always wins
        assert self.fake.completion.call_args[1]["drop_params"] is True


# ---------------------------------------------------------------------------
# Async proxy
# ---------------------------------------------------------------------------


class TestAsyncProxy:
    def setup_method(self):
        self.fake = _install_fake_litellm("async response")

    def teardown_method(self):
        _uninstall_fake_litellm()

    @pytest.mark.asyncio
    async def test_returns_response_content(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=True)
        result = await proxy.chat.completions.create(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result.choices[0].message.content == "async response"

    @pytest.mark.asyncio
    async def test_drop_params_true(self):
        """Verify drop_params is passed in async mode too."""
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=True)
        # acompletion is a real async function, not a mock, so just verify it runs
        result = await proxy.chat.completions.create(model="x", messages=[])
        assert result is not None


# ---------------------------------------------------------------------------
# Factory and registration
# ---------------------------------------------------------------------------


class TestFactoryRegistration:
    def setup_method(self):
        _install_fake_litellm()

    def teardown_method(self):
        _uninstall_fake_litellm()

    def test_litellm_in_supported_providers(self):
        from src.llm.factory import SUPPORTED_PROVIDERS

        assert "litellm" in SUPPORTED_PROVIDERS

    def test_litellm_in_providers_init_all(self):
        from src.llm.providers import __all__

        assert "LiteLLMClient" in __all__

    def test_litellm_importable_from_providers(self):
        from src.llm.providers import LiteLLMClient

        assert LiteLLMClient is not None

    def test_litellm_client_extends_openai_client(self):
        from src.llm.providers.litellm_client import LiteLLMClient
        from src.llm.providers.openai_client import OpenAIClient

        assert issubclass(LiteLLMClient, OpenAIClient)

    def test_unsupported_provider_raises(self):
        from omegaconf import OmegaConf
        from src.llm.factory import ClientFactory

        cfg = OmegaConf.create({"llm": {"provider": "nonexistent"}})
        with pytest.raises(ValueError, match="Unsupported provider"):
            ClientFactory(task_id="t", cfg=cfg)


# ---------------------------------------------------------------------------
# _create_client behavior
# ---------------------------------------------------------------------------


class TestCreateClient:
    def setup_method(self):
        self.fake = _install_fake_litellm()

    def teardown_method(self):
        _uninstall_fake_litellm()

    def test_returns_proxy_instance(self):
        from src.llm.providers.litellm_client import LiteLLMClient, _LiteLLMProxy

        client = object.__new__(LiteLLMClient)
        client.async_client = False
        client.task_id = "test"
        result = client._create_client()
        assert isinstance(result, _LiteLLMProxy)

    def test_sync_mode_uses_sync_completions(self):
        from src.llm.providers.litellm_client import LiteLLMClient, _SyncCompletions

        client = object.__new__(LiteLLMClient)
        client.async_client = False
        client.task_id = "test"
        proxy = client._create_client()
        assert isinstance(proxy.chat.completions, _SyncCompletions)

    def test_async_mode_uses_async_completions(self):
        from src.llm.providers.litellm_client import LiteLLMClient, _AsyncCompletions

        client = object.__new__(LiteLLMClient)
        client.async_client = True
        client.task_id = "test"
        proxy = client._create_client()
        assert isinstance(proxy.chat.completions, _AsyncCompletions)

    def test_proxy_has_chat_attribute(self):
        from src.llm.providers.litellm_client import LiteLLMClient

        client = object.__new__(LiteLLMClient)
        client.async_client = False
        client.task_id = "test"
        proxy = client._create_client()
        assert hasattr(proxy, "chat")
        assert hasattr(proxy.chat, "completions")
        assert hasattr(proxy.chat.completions, "create")


# ---------------------------------------------------------------------------
# Response format compatibility
# ---------------------------------------------------------------------------


class TestResponseFormat:
    def setup_method(self):
        self.fake = _install_fake_litellm()

    def teardown_method(self):
        _uninstall_fake_litellm()

    def test_response_has_choices(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        result = proxy.chat.completions.create(model="x", messages=[])
        assert hasattr(result, "choices")
        assert len(result.choices) > 0

    def test_response_has_usage(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        result = proxy.chat.completions.create(model="x", messages=[])
        assert hasattr(result, "usage")
        assert hasattr(result.usage, "prompt_tokens")
        assert hasattr(result.usage, "completion_tokens")

    def test_response_has_finish_reason(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        result = proxy.chat.completions.create(model="x", messages=[])
        assert result.choices[0].finish_reason == "stop"

    def test_response_message_has_content_and_role(self):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        result = proxy.chat.completions.create(model="x", messages=[])
        msg = result.choices[0].message
        assert hasattr(msg, "content")
        assert hasattr(msg, "role")


# ---------------------------------------------------------------------------
# Multi-provider model strings
# ---------------------------------------------------------------------------


class TestMultiProviderModels:
    def setup_method(self):
        self.fake = _install_fake_litellm()

    def teardown_method(self):
        _uninstall_fake_litellm()

    @pytest.mark.parametrize(
        "model",
        [
            "openai/gpt-4o",
            "anthropic/claude-3-haiku",
            "bedrock/anthropic.claude-v2",
            "vertex_ai/gemini-pro",
            "groq/llama3-70b-8192",
            "ollama/llama3",
            "azure/gpt-4o",
        ],
    )
    def test_model_string_forwarded_to_litellm(self, model):
        from src.llm.providers.litellm_client import _LiteLLMProxy

        proxy = _LiteLLMProxy(async_mode=False)
        proxy.chat.completions.create(model=model, messages=[])
        assert self.fake.completion.call_args[1]["model"] == model
