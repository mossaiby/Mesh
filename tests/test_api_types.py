import asyncio
import types

import pytest

from config import ModelConfig, ProviderConfig, ConfigManager, MeshConfig, normalize_api_type
from providers import (
    resolve_api_type, get_provider, OpenAIProvider, OpenAIResponsesProvider, AnthropicProvider,
)
from providers.anthropic_provider import anthropic_client_kwargs


def _prov(url="http://localhost:1234/v1", name="LM Studio", api_type="auto"):
    return ProviderConfig(name=name, base_url=url, api_type=api_type)


def _model(provider="lmstudio", api_type="auto"):
    return ModelConfig(name="m", provider=provider, model_id="m1", api_type=api_type)


def test_normalize_aliases_and_errors():
    assert normalize_api_type("Responses") == "openai-responses"
    assert normalize_api_type("OPENAI_CHAT") == "openai-chat"
    assert normalize_api_type("messages") == "anthropic"
    assert normalize_api_type(None) == "auto"
    with pytest.raises(ValueError):
        normalize_api_type("grpc")
    with pytest.raises(ValueError):
        _model(api_type="bogus")


def test_resolution_order():
    assert resolve_api_type(_model(), _prov()) == "openai-chat"                       # detection
    assert resolve_api_type(_model(provider="anthropic"), _prov("https://api.anthropic.com", "Anthropic")) == "anthropic"
    assert resolve_api_type(_model(), _prov(api_type="openai-responses")) == "openai-responses"  # provider
    assert resolve_api_type(_model(api_type="anthropic"), _prov(api_type="openai-responses")) == "anthropic"  # model wins
    # explicit chat overrides Anthropic detection
    assert resolve_api_type(_model(provider="anthropic", api_type="openai-chat"), _prov("https://api.anthropic.com", "Anthropic")) == "openai-chat"


def test_factory_picks_class():
    assert type(get_provider(_model(), _prov())) is OpenAIProvider
    assert type(get_provider(_model(api_type="openai-responses"), _prov())) is OpenAIResponsesProvider
    assert type(get_provider(_model(api_type="anthropic"), _prov())) is AnthropicProvider


def test_anthropic_base_url_strips_v1():
    assert anthropic_client_kwargs(_prov("http://localhost:1234/v1"))["base_url"] == "http://localhost:1234"
    assert anthropic_client_kwargs(_prov("http://localhost:1234/v1/"))["base_url"] == "http://localhost:1234"
    assert anthropic_client_kwargs(_prov("http://localhost:1234"))["base_url"] == "http://localhost:1234"
    assert "base_url" not in anthropic_client_kwargs(_prov("https://api.anthropic.com", "Anthropic"))


def test_config_roundtrip_and_setters(temp_workspace):
    import os
    path = os.path.join(temp_workspace, "config.json")
    mgr = ConfigManager(path) if os.path.exists(path) else None
    if mgr is None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(MeshConfig(active_model="p:m").model_dump_json(indent=2, by_alias=True))
        mgr = ConfigManager(path)
    mgr.add_provider("p", "P", "http://x/v1", api_type="openai-responses")
    mgr.add_model("p:m", "p", "m", api_type="anthropic")
    mgr2 = ConfigManager(path)
    assert mgr2.config.providers["p"].api_type == "openai-responses"
    assert mgr2.config.models["p:m"].api_type == "anthropic"
    assert mgr2.set_model_api_type("p:m", "chat") == "openai-chat"
    assert mgr2.set_provider_api_type("p", "auto") == "auto"
    assert ConfigManager(path).config.models["p:m"].api_type == "openai-chat"
    with pytest.raises(ValueError):
        mgr2.set_model_api_type("p:m", "nope")
    with pytest.raises(KeyError):
        mgr2.set_model_api_type("missing", "auto")


def test_old_config_without_api_type_loads():
    m = ModelConfig.model_validate({"name": "n", "provider": "p", "model_id": "x"})
    assert m.api_type == "auto"


# ---------------------------------------------------------------- Responses provider
def _ns(**kw):
    return types.SimpleNamespace(**kw)


def test_responses_message_and_tool_conversion():
    prov = get_provider(_model(api_type="openai-responses"), _prov())
    msgs = [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "calling", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"a":1}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "done"},
        {"role": "user", "content": [{"type": "text", "text": "see"},
                                     {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]},
    ]
    instr, items = prov._convert_messages(msgs)
    assert instr == "be nice"
    assert items[0] == {"role": "user", "content": "hi"}
    assert items[1] == {"role": "assistant", "content": "calling"}
    assert items[2] == {"type": "function_call", "call_id": "c1", "name": "f", "arguments": '{"a":1}'}
    assert items[3] == {"type": "function_call_output", "call_id": "c1", "output": "done"}
    assert items[4]["content"] == [{"type": "input_text", "text": "see"},
                                   {"type": "input_image", "image_url": "data:image/png;base64,AA"}]

    tools = prov._convert_tools([{"type": "function", "function": {"name": "f", "description": "d", "parameters": {"type": "object"}}}])
    assert tools == [{"type": "function", "name": "f", "description": "d", "parameters": {"type": "object"}}]


class _FakeStream:
    def __init__(self, events):
        self.events = events

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e
        return gen()


def _collect(prov, events, tools=None):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return _FakeStream(events)

    prov.client = _ns(responses=_ns(create=create))

    async def run():
        return [e async for e in prov.stream_chat([{"role": "user", "content": "hi"}], tools)]

    return asyncio.run(run()), captured


def test_responses_stream_text_reasoning_tools_usage():
    prov = get_provider(_model(api_type="openai-responses"), _prov())
    fc = _ns(type="function_call", call_id="call_9", id="fc_1", name="lookup", arguments="")
    events = [
        _ns(type="response.reasoning_summary_text.delta", delta="think"),
        _ns(type="response.output_text.delta", delta="Hel"),
        _ns(type="response.output_text.delta", delta="lo"),
        _ns(type="response.output_item.added", output_index=1, item=fc),
        _ns(type="response.function_call_arguments.delta", output_index=1, delta='{"q":'),
        _ns(type="response.function_call_arguments.delta", output_index=1, delta='"x"}'),
        _ns(type="response.function_call_arguments.done", output_index=1, arguments='{"q":"x"}'),
        _ns(type="response.output_item.done", output_index=1, item=_ns(type="function_call", call_id="call_9", id="fc_1", name="lookup", arguments='{"q":"x"}')),
        _ns(type="response.completed", response=_ns(usage=_ns(input_tokens=10, output_tokens=5,
                                                              input_tokens_details=_ns(cached_tokens=3)))),
    ]
    out, kwargs = _collect(prov, events, tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}])
    assert kwargs["stream"] is True and kwargs["tool_choice"] == "auto" and kwargs["tools"][0]["name"] == "lookup"
    assert [e["value"] for e in out if e["type"] == "content"] == ["Hel", "lo"]
    assert [e["value"] for e in out if e["type"] == "reasoning"] == ["think"]
    calls = [e["value"][0] for e in out if e["type"] == "tool_calls"]
    assert calls[0] == {"index": 0, "id": "call_9", "function": {"name": "lookup", "arguments": ""}}
    assert "".join(c["function"]["arguments"] for c in calls[1:]) == '{"q":"x"}'  # not duplicated by .done
    assert out[-1] == {"type": "usage", "value": {"prompt_tokens": 10, "completion_tokens": 5, "cached_tokens": 3}}


def test_responses_stream_call_only_in_done_event():
    prov = get_provider(_model(api_type="openai-responses"), _prov())
    item = _ns(type="function_call", call_id="c7", id="fc", name="t", arguments='{"a":2}')
    out, _ = _collect(prov, [_ns(type="response.output_item.done", output_index=0, item=item)])
    calls = [e["value"][0] for e in out if e["type"] == "tool_calls"]
    assert calls[0]["id"] == "c7" and calls[0]["function"]["name"] == "t"
    assert calls[1]["function"]["arguments"] == '{"a":2}'


def test_responses_stream_failure_raises():
    prov = get_provider(_model(api_type="openai-responses"), _prov())
    ev = _ns(type="response.failed", response=_ns(error=_ns(message="boom")))
    with pytest.raises(RuntimeError, match="boom"):
        _collect(prov, [ev])


# ---------------------------------------------------------------- commands
def _cmd_engine(temp_workspace):
    import os
    from commands.model_commands import cmd_providers, cmd_models
    path = os.path.join(temp_workspace, "cmdcfg.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(MeshConfig(active_model="p:m").model_dump_json(indent=2, by_alias=True))
    mgr = ConfigManager(path)
    return types.SimpleNamespace(config_mgr=mgr), cmd_providers, cmd_models


def test_provider_and_model_commands_set_api_type(temp_workspace):
    eng, cmd_providers, cmd_models = _cmd_engine(temp_workspace)
    asyncio.run(cmd_providers(eng, ["add", "lm", "http://localhost:1234/v1", "--api", "responses"]))
    assert eng.config_mgr.config.providers["lm"].api_type == "openai-responses"

    asyncio.run(cmd_providers(eng, ["add", "lm2", "--api=anthropic", "http://localhost:1234/v1", "LM Two", "LM2_KEY"]))
    p2 = eng.config_mgr.config.providers["lm2"]
    assert (p2.api_type, p2.name, p2.api_key_env) == ("anthropic", "LM Two", "LM2_KEY")

    eng.config_mgr.add_model("lm:x", "lm", "x")
    asyncio.run(cmd_models(eng, ["api", "lm:x", "anthropic"]))
    assert eng.config_mgr.config.models["lm:x"].api_type == "anthropic"
    asyncio.run(cmd_providers(eng, ["api", "lm", "openai-chat"]))
    assert eng.config_mgr.config.providers["lm"].api_type == "openai-chat"

    # invalid values leave config untouched
    asyncio.run(cmd_models(eng, ["api", "lm:x", "bogus"]))
    assert eng.config_mgr.config.models["lm:x"].api_type == "anthropic"
    asyncio.run(cmd_providers(eng, ["add", "bad", "http://x/v1", "--api", "bogus"]))
    assert "bad" not in eng.config_mgr.config.providers


def test_models_add_applies_api_flag(temp_workspace, monkeypatch):
    import commands.model_commands as mc
    eng, _, cmd_models = _cmd_engine(temp_workspace)
    eng.config_mgr.add_provider("lm", "LM", "http://localhost:1234/v1")
    eng.config_mgr.config.timeouts.api = 1

    async def fake_fetch(*a, **k):
        return True, [{"id": "a", "name": "A", "context_window": 4096, "description": ""}], ""

    async def fake_ctx(**k):
        return 4096

    monkeypatch.setattr(mc, "fetch_models_details", fake_fetch)
    monkeypatch.setattr(mc, "infer_context_window", fake_ctx)
    asyncio.run(cmd_models(eng, ["add", "lm", "*", "--api", "anthropic"]))
    assert eng.config_mgr.config.models["lm:a"].api_type == "anthropic"
