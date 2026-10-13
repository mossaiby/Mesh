"""
The queue Mesh's interactive loop consumes from, plus the event registry
that backs resumable tool calls.

WHY THIS EXISTS: some tool calls - most importantly MCP servers that ask
the user to go do something outside the chat entirely (finish an OAuth
flow in a browser, restart a service, wait for a build) - previously had
no way to end their turn and pick back up automatically once that external
thing happened. The only mechanism was the user manually typing "continue"
once they'd finished. This module makes "the tool call is pending an
external event" a first-class state: a tool returns
`{"status": "pending", "event_id": ..., "message": ...}`, Mesh ends the
turn normally, and whenever that event_id is later fired - by `/resume`,
by a background watcher (see `EventRegistry.watch_file`), or by anything
else that calls `EventRegistry.fire()` - a resume item is queued and
picked up automatically the next time Mesh is idle. No "continue" needed.

QUEUEING, NOT JUST RESUMING: user input goes through the exact same queue
as resume events, because an event can fire while a turn is already in
progress, and handling it inline would race against whatever's currently
running. Everything - a typed message, a resume event - becomes a
`QueueItem` and is consumed one at a time, in arrival order, only when
Mesh is idle.

SCOPE, stated plainly: idle-time racing (waiting at an empty prompt, an
event fires, it's picked up immediately rather than waiting for the user
to type something unrelated) is fully implemented and tested. Free-text
out-of-band commands typed *while a turn is actively streaming* are NOT -
that needs concurrent terminal input+output rendering (prompt_toolkit and
Rich drawing at once), a substantially different and riskier UI problem
that can't be responsibly validated without a real interactive terminal.
What IS implemented for "interrupt a running turn": Ctrl+C during an
active turn cancels just that turn and returns to the queue, rather than
quitting Mesh - see engine.py's _run_turn.
"""

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class QueueItem:
    kind: str  # "user_input" | "resume_event"
    payload: Any
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: float = field(default_factory=time.monotonic)


class TurnQueue:
    """A single FIFO queue of QueueItems. User input and resume events are
    both just items - the consumer doesn't need to know which kind is
    coming next until it arrives."""

    def __init__(self):
        self.queue: "asyncio.Queue[QueueItem]" = asyncio.Queue()

    async def put_input(self, text: str) -> QueueItem:
        item = QueueItem(kind="user_input", payload=text)
        await self.queue.put(item)
        return item

    async def put_resume(self, event_id: str, note: str = "") -> QueueItem:
        item = QueueItem(kind="resume_event", payload={"event_id": event_id, "note": note})
        await self.queue.put(item)
        return item

    def empty(self) -> bool:
        return self.queue.empty()

    async def get(self) -> QueueItem:
        return await self.queue.get()


class EventRegistry:
    """Tracks tool calls waiting on an external event, and whatever
    background mechanism (if any) is watching for it automatically.
    `fire()` is the single choke point: `/resume` calls it manually,
    `watch_file`'s poller calls it automatically, and anything else (an
    HTTP callback, an MCP resource subscription) would call it the same
    way."""

    def __init__(self, turn_queue: TurnQueue):
        self._turn_queue = turn_queue
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._watchers: Dict[str, "asyncio.Task"] = {}

    def register(self, event_id: str, message: str = "", tool_name: str = "") -> None:
        """Marks event_id as awaited. Re-registering the same id just
        refreshes its metadata."""
        self._pending[event_id] = {
            "message": message,
            "tool_name": tool_name,
            "registered_at": time.monotonic(),
        }

    def is_pending(self, event_id: str) -> bool:
        return event_id in self._pending

    def list_pending(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._pending)

    async def fire(self, event_id: str, note: str = "") -> bool:
        """Resolves a pending event: cancels its watcher, removes it from
        the pending set, queues a resume item. Returns False (a no-op) if
        event_id isn't pending - so a watcher racing a manual /resume
        can't double-fire."""
        if event_id not in self._pending:
            return False
        self._pending.pop(event_id)
        self._cancel_watcher(event_id)
        await self._turn_queue.put_resume(event_id, note or f"Event '{event_id}' fired.")
        return True

    def cancel(self, event_id: str) -> bool:
        """Removes a pending event WITHOUT firing it."""
        if event_id not in self._pending:
            return False
        del self._pending[event_id]
        self._cancel_watcher(event_id)
        return True

    def watch_file(self, event_id: str, path: str, poll_interval: float = 1.0) -> None:
        """Fires `event_id` the moment `path` exists - the simplest
        automatic trigger (a build writing a marker file, a download
        completing). event_id must already be registered."""
        if event_id in self._watchers:
            self._cancel_watcher(event_id)

        async def _watch():
            try:
                while self.is_pending(event_id):
                    if os.path.exists(path):
                        await self.fire(event_id, f"File '{path}' now exists.")
                        return
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                pass

        self._watchers[event_id] = asyncio.create_task(_watch())

    def _cancel_watcher(self, event_id: str) -> None:
        task = self._watchers.pop(event_id, None)
        if task and not task.done():
            task.cancel()

    def shutdown(self) -> None:
        """Cancels every active watcher (called at session end)."""
        for event_id in list(self._watchers.keys()):
            self._cancel_watcher(event_id)
