import asyncio
import types

import pytest

import inference_coordinator as ic
from inference_coordinator import InferenceCoordinator


class _Logger:
    def __init__(self):
        self.events = []

    def log_system_event(self, text):
        self.events.append(text)

    def log_assistant_response(self, *a, **k):
        pass


class _Renderer:
    async def render_stream(self, gen, debug_mode=False):
        text = ""
        async for chunk in gen:
            if chunk["type"] == "content":
                text += chunk["value"]
        return text, ""


class _Provider:
    """Requests a tool on every call until `finish_after` calls have happened."""
    def __init__(self, finish_after=None):
        self.calls = 0
        self.finish_after = finish_after

    async def stream_chat(self, messages, tools=None):
        self.calls += 1
        if self.finish_after is not None and self.calls > self.finish_after:
            yield {"type": "content", "value": "all done"}
            return
        yield {"type": "tool_calls", "value": [{"index": 0, "id": f"c{self.calls}", "function": {"name": "t", "arguments": "{}"}}]}


class _Orchestrator:
    def __init__(self):
        self.runs = 0

    async def execute_tool_calls(self, calls, messages):
        for c in calls:
            self.runs += 1
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": "ok"})


def _setup(monkeypatch, max_turns, provider):
    cfg = types.SimpleNamespace(
        active_model="m",
        turns=types.SimpleNamespace(engine=max_turns),
        show_tokens=False, show_cost=False, show_statistics=False,
    )
    model = types.SimpleNamespace(name="M", model_id="m")
    prov = types.SimpleNamespace(name="P", base_url="http://x")
    mgr = types.SimpleNamespace(config=cfg, get_active_model_and_provider=lambda: (model, prov))
    orch = _Orchestrator()
    engine = types.SimpleNamespace(
        config_mgr=mgr, messages=[{"role": "user", "content": "go"}], is_running=True, tools_enabled=True,
        tool_registry=types.SimpleNamespace(get_schemas=lambda: [{"function": {"name": "t"}}], mode_blocked_tools=set()),
        session_logger=_Logger(), renderer=_Renderer(), debug_mode=False, tool_orchestrator=orch,
        session_prompt_tokens=0, session_completion_tokens=0, session_cached_tokens=0, session_cost_usd=0.0,
    )

    async def no_compact(messages, config_mgr):
        return messages, False, ""

    monkeypatch.setattr(ic, "get_provider", lambda *a, **k: provider)
    monkeypatch.setattr(ic, "maybe_auto_compact", no_compact)
    return InferenceCoordinator(engine), engine, orch


def _keys(monkeypatch, *keys):
    seq = list(keys)
    asked = []
    monkeypatch.setattr(ic.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(ic, "_read_single_key", lambda: asked.append(1) or seq.pop(0))
    return asked


def test_stop_at_limit(monkeypatch):
    prov = _Provider()
    coord, engine, orch = _setup(monkeypatch, 2, prov)
    asked = _keys(monkeypatch, "s")
    asyncio.run(coord.process_inference())
    assert prov.calls == 2 and orch.runs == 2 and len(asked) == 1
    assert any("Stopped at turn limit" in e for e in engine.session_logger.events)


def test_continue_grants_another_batch_then_finishes(monkeypatch):
    prov = _Provider(finish_after=3)   # needs 4 model calls; limit is 2 per batch
    coord, engine, orch = _setup(monkeypatch, 2, prov)
    asked = _keys(monkeypatch, "c")
    asyncio.run(coord.process_inference())
    assert prov.calls == 4 and len(asked) == 1
    assert engine.messages[-1] == {"role": "assistant", "content": "all done"}


@pytest.mark.parametrize("first,expected_calls", [("enter", 4), ("y", 4), ("escape", 2), ("n", 2), ("q", 2)])
def test_key_variants(monkeypatch, first, expected_calls):
    prov = _Provider(finish_after=3)
    coord, engine, orch = _setup(monkeypatch, 2, prov)
    _keys(monkeypatch, first)
    asyncio.run(coord.process_inference())
    assert prov.calls == expected_calls


def test_ignores_other_keys_until_valid(monkeypatch):
    prov = _Provider()
    coord, engine, orch = _setup(monkeypatch, 1, prov)
    asked = _keys(monkeypatch, "x", "z", "s")
    asyncio.run(coord.process_inference())
    assert len(asked) == 3 and prov.calls == 1


def test_no_prompt_when_model_finishes_within_limit(monkeypatch):
    prov = _Provider(finish_after=1)
    coord, engine, orch = _setup(monkeypatch, 5, prov)
    asked = _keys(monkeypatch)  # any key read would raise IndexError
    asyncio.run(coord.process_inference())
    assert prov.calls == 2 and not asked


def test_no_prompt_when_finishing_exactly_on_last_turn(monkeypatch):
    prov = _Provider(finish_after=1)
    coord, engine, orch = _setup(monkeypatch, 2, prov)   # turn 2 is the final text answer
    asked = _keys(monkeypatch)
    asyncio.run(coord.process_inference())
    assert prov.calls == 2 and not asked


def test_non_interactive_stops_without_prompt(monkeypatch):
    prov = _Provider()
    coord, engine, orch = _setup(monkeypatch, 2, prov)
    monkeypatch.setattr(ic.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr(ic, "_read_single_key", lambda: pytest.fail("must not prompt"))
    asyncio.run(coord.process_inference())
    assert prov.calls == 2


def test_ctrl_c_at_prompt_stops_and_keeps_history(monkeypatch):
    prov = _Provider()
    coord, engine, orch = _setup(monkeypatch, 1, prov)
    monkeypatch.setattr(ic.sys.stdin, "isatty", lambda: True, raising=False)

    def boom():
        raise KeyboardInterrupt()

    monkeypatch.setattr(ic, "_read_single_key", boom)
    asyncio.run(coord.process_inference())
    assert prov.calls == 1
    assert engine.messages[-1]["role"] == "tool"   # work kept, not rolled back
