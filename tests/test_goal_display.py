import asyncio
import types

import pytest

from tools.goal_tool import GoalTool
from commands.session_commands import cmd_goal


class _Console:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))

    def text(self):
        return "\n".join(self.lines)


def _tool():
    con = _Console()
    changes = []
    tool = GoalTool(on_change=lambda: changes.append(1), on_display=lambda changed: tool.show(con, cleared=changed))
    return tool, con, changes


def run(coro):
    return asyncio.run(coro)


def test_set_displays_goal_and_criteria():
    tool, con, _ = _tool()
    run(tool.execute("set", goal="Ship export", success_criteria=["tests pass", "docs"]))
    out = con.text()
    assert "Ship export" in out and "tests pass" in out and "0/2 criteria met" in out


def test_complete_criterion_displays_update():
    tool, con, _ = _tool()
    run(tool.execute("set", goal="G", success_criteria=["a", "b"]))
    con.lines.clear()
    run(tool.execute("complete_criterion", criterion_index=1))
    assert "1/2 criteria met" in con.text()


def test_clear_announces_removal_once():
    tool, con, _ = _tool()
    run(tool.execute("set", goal="G"))
    con.lines.clear()
    run(tool.execute("clear"))
    assert con.lines == ["[warning]Goal cleared.[/warning]"]


def test_no_display_when_nothing_changed():
    tool, con, changes = _tool()
    run(tool.execute("set", goal="G", success_criteria=["a"]))
    con.lines.clear()
    run(tool.execute("set", goal="G", success_criteria=["a"]))        # identical
    run(tool.execute("get"))
    run(tool.execute("clear"))                                         # real change
    con.lines.clear()
    run(tool.execute("clear"))                                         # already clear
    assert con.lines == []
    assert len(changes) >= 3                                           # system prompt still refreshed


def test_display_action_renders_even_without_change():
    tool, con, _ = _tool()
    run(tool.execute("set", goal="G"))
    con.lines.clear()
    res = run(tool.execute("display"))
    assert res["status"] == "displayed" and "G" in con.text()


def test_restore_notify_displays_only_if_different():
    tool, con, _ = _tool()
    run(tool.execute("set", goal="G"))
    con.lines.clear()
    tool._notify()                       # e.g. checkpoint restore of identical state
    assert con.lines == []
    tool._goal = "Other"                 # checkpoint/session restore sets fields then notifies
    tool._criteria = []
    tool._notify()
    assert "Other" in con.text()


def _engine():
    tool, con, _ = _tool()
    return types.SimpleNamespace(goal_tool=tool), con


@pytest.fixture
def patched_console(monkeypatch):
    import commands.session_commands as sc
    con = _Console()
    monkeypatch.setattr(sc, "console", con)
    return con


def test_command_set_shows_goal_once(patched_console):
    eng, tool_con = _engine()
    run(cmd_goal(eng, ["Ship", "it", "|", "tests", "|", "docs"]))
    assert tool_con.text().count("Current Goal") == 1
    assert patched_console.lines == []             # command adds no duplicate rendering


def test_command_set_same_goal_still_shows(patched_console):
    eng, tool_con = _engine()
    run(cmd_goal(eng, ["Same"]))
    tool_con.lines.clear()
    patched_console.lines.clear()
    run(cmd_goal(eng, ["Same"]))
    assert any("Same" in l for l in patched_console.lines)


def test_command_done_and_clear(patched_console):
    eng, tool_con = _engine()
    run(cmd_goal(eng, ["G", "|", "a", "|", "b"]))
    tool_con.lines.clear()
    run(cmd_goal(eng, ["done", "1"]))
    assert "1/2 criteria met" in tool_con.text()
    assert any("Marked criterion #1" in l for l in patched_console.lines)
    tool_con.lines.clear()
    patched_console.lines.clear()
    run(cmd_goal(eng, ["clear"]))
    assert tool_con.lines == ["[warning]Goal cleared.[/warning]"]
    assert patched_console.lines == []             # no second "cleared" message
    run(cmd_goal(eng, ["clear"]))
    assert any("No goal" in l for l in patched_console.lines)


def test_real_engine_displays_goal_changes(monkeypatch):
    """The real MeshEngine passes a display hook that prints through the themed console."""
    import engine as engine_mod
    printed = []
    monkeypatch.setattr(engine_mod.console, "print", lambda *a, **k: printed.append(" ".join(map(str, a))))
    eng = engine_mod.MeshEngine()
    run(eng.goal_tool.execute("set", goal="Wired up", success_criteria=["one"]))
    assert any("Wired up" in l for l in printed)
    printed.clear()
    run(eng.goal_tool.execute("complete_criterion", criterion_index=1))
    assert any("1/1 criteria met" in l for l in printed)
    printed.clear()
    run(eng.goal_tool.execute("clear"))
    assert printed == ["[warning]Goal cleared.[/warning]"]
