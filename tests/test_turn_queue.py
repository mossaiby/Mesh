import asyncio
import json
import os

import pytest

from tools.registry import ToolRegistry
from tools.wait_for_event_tool import WaitForEventTool
from turn_queue import EventRegistry, QueueItem, TurnQueue


@pytest.mark.asyncio
async def test_register_and_fire_queues_a_resume_item():
    tq = TurnQueue()
    er = EventRegistry(tq)
    er.register("evt1", "waiting on oauth", "some_tool")
    assert er.is_pending("evt1")

    assert await er.fire("evt1", "done!") is True
    assert not er.is_pending("evt1")

    item = await tq.get()
    assert item.kind == "resume_event"
    assert item.payload == {"event_id": "evt1", "note": "done!"}


@pytest.mark.asyncio
async def test_firing_unknown_event_is_a_noop():
    tq = TurnQueue()
    er = EventRegistry(tq)
    assert await er.fire("nope") is False
    assert tq.empty()


@pytest.mark.asyncio
async def test_firing_twice_only_queues_once():
    """A background watcher racing a manual /resume must not double-fire."""
    tq = TurnQueue()
    er = EventRegistry(tq)
    er.register("evt1")
    assert await er.fire("evt1") is True
    assert await er.fire("evt1") is False
    await tq.get()
    assert tq.empty()


@pytest.mark.asyncio
async def test_cancel_removes_without_firing():
    tq = TurnQueue()
    er = EventRegistry(tq)
    er.register("evt1")
    assert er.cancel("evt1") is True
    assert not er.is_pending("evt1")
    assert tq.empty()
    assert er.cancel("evt1") is False


@pytest.mark.asyncio
async def test_input_and_resume_items_are_consumed_in_arrival_order():
    """The whole reason user input shares a queue with resume events: an
    event firing while a turn is in progress must not jump ahead of, or
    get lost behind, anything else."""
    tq = TurnQueue()
    await tq.put_input("first")
    await tq.put_resume("evt", "second")
    await tq.put_input("third")

    kinds = [(await tq.get()).kind for _ in range(3)]
    assert kinds == ["user_input", "resume_event", "user_input"]


@pytest.mark.asyncio
async def test_watch_file_fires_when_the_file_appears(tmp_path):
    tq = TurnQueue()
    er = EventRegistry(tq)
    marker = tmp_path / "done.marker"
    er.register("build", "waiting on build")
    er.watch_file("build", str(marker), poll_interval=0.05)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(tq.get(), timeout=0.2)  # must not fire early

    marker.write_text("done")
    item = await asyncio.wait_for(tq.get(), timeout=2.0)
    assert item.payload["event_id"] == "build"
    assert not er.is_pending("build")
    er.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_watchers(tmp_path):
    tq = TurnQueue()
    er = EventRegistry(tq)
    er.register("e")
    er.watch_file("e", str(tmp_path / "never"), poll_interval=0.05)
    er.shutdown()
    await asyncio.sleep(0.15)
    assert er.is_pending("e")  # still registered...
    assert tq.empty()  # ...but its watcher is gone and never fired


@pytest.mark.asyncio
async def test_wait_for_event_tool_returns_the_pending_shape():
    tool = WaitForEventTool()
    result = await tool.execute(message="finish login", event_id="login", watch_file="/tmp/x")
    assert result == {"status": "pending", "event_id": "login", "message": "finish login", "watch_file": "/tmp/x"}

    auto = await tool.execute(message="something")
    assert auto["status"] == "pending"
    assert auto["event_id"].startswith("wait-")
    assert "watch_file" not in auto


@pytest.mark.asyncio
async def test_registry_auto_registers_pending_results_from_any_tool(tmp_path):
    """The contract is generic: ANY tool returning {"status": "pending",
    ...} gets registered - not just wait_for_event."""
    from tools.base import BaseTool

    class CustomPendingTool(BaseTool):
        name = "custom_pending"
        description = "returns pending"
        parameters = {"type": "object", "properties": {}}

        async def execute(self):
            return {"status": "pending", "event_id": "custom-evt", "message": "do the thing"}

    tq = TurnQueue()
    er = EventRegistry(tq)
    registry = ToolRegistry()
    registry.register(CustomPendingTool())
    registry.event_registry = er

    result = await registry.execute("custom_pending", json.dumps({}))
    assert json.loads(result)["status"] == "pending"  # model still sees it
    assert er.is_pending("custom-evt")
    assert er.list_pending()["custom-evt"]["tool_name"] == "custom_pending"


@pytest.mark.asyncio
async def test_registry_starts_a_file_watcher_when_asked(tmp_path):
    tq = TurnQueue()
    er = EventRegistry(tq)
    registry = ToolRegistry()
    registry.register(WaitForEventTool())
    registry.event_registry = er

    marker = tmp_path / "ready"
    await registry.execute(
        "wait_for_event",
        json.dumps({"message": "waiting", "event_id": "ready-evt", "watch_file": str(marker)}),
    )
    assert er.is_pending("ready-evt")

    marker.write_text("x")
    item = await asyncio.wait_for(tq.get(), timeout=3.0)
    assert item.payload["event_id"] == "ready-evt"
    er.shutdown()


@pytest.mark.asyncio
async def test_non_pending_results_are_not_registered():
    from tools.registry import CalculatorTool

    tq = TurnQueue()
    er = EventRegistry(tq)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.event_registry = er

    await registry.execute("calculator", json.dumps({"expression": "1+1"}))
    assert er.list_pending() == {}


class _FakeEngine:
    """Just enough of MeshEngine to exercise _wait_for_next_action's race
    logic in isolation, without needing a real terminal or model."""

    def __init__(self, prompt_coro_factory):
        self.turn_queue = TurnQueue()

        class _PromptSession:
            get_input_async = staticmethod(prompt_coro_factory)

        self.prompt_session = _PromptSession()


@pytest.mark.asyncio
async def test_idle_wait_returns_typed_input_when_user_types_first():
    from engine import MeshEngine

    async def prompt():
        await asyncio.sleep(0.05)
        return "hello"

    fake = _FakeEngine(prompt)
    item = await MeshEngine._wait_for_next_action(fake)
    assert item.kind == "user_input"
    assert item.payload == "hello"


@pytest.mark.asyncio
async def test_idle_wait_picks_up_an_event_that_fires_while_sitting_at_the_prompt():
    """The core scenario this whole feature exists for: Mesh is idle at an
    empty prompt, the user has typed nothing, and an external event fires -
    it must be picked up immediately, not wait for unrelated input."""
    from engine import MeshEngine

    prompt_cancelled = asyncio.Event()

    async def prompt():
        try:
            await asyncio.sleep(30)  # user never types anything
        except asyncio.CancelledError:
            prompt_cancelled.set()
            raise

    fake = _FakeEngine(prompt)

    async def fire_later():
        await asyncio.sleep(0.1)
        await fake.turn_queue.put_resume("oauth", "login complete")

    asyncio.create_task(fire_later())
    item = await asyncio.wait_for(MeshEngine._wait_for_next_action(fake), timeout=3.0)

    assert item.kind == "resume_event"
    assert item.payload["event_id"] == "oauth"
    assert prompt_cancelled.is_set()  # the stale prompt didn't get left hanging


@pytest.mark.asyncio
async def test_idle_wait_takes_an_already_queued_item_without_prompting():
    from engine import MeshEngine

    prompted = []

    async def prompt():
        prompted.append(True)
        await asyncio.sleep(30)

    fake = _FakeEngine(prompt)
    await fake.turn_queue.put_resume("already", "queued while a turn was running")
    item = await MeshEngine._wait_for_next_action(fake)

    assert item.kind == "resume_event"
    assert prompted == []  # never even started a prompt
