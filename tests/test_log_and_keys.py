import asyncio
import types

import pytest

from commands.registry import CommandRegistry
from commands.session_commands import cmd_log


class _Logger:
    def __init__(self):
        self.enabled = False
        self.filepath = "session.md"

    def enable(self, path=None):
        if path:
            self.filepath = path
        self.enabled = True

    def disable(self):
        self.enabled = False


def _engine():
    cfg = types.SimpleNamespace(enabled=False, filepath="session.md")
    saved = []
    eng = types.SimpleNamespace(
        session_logger=_Logger(),
        config_mgr=types.SimpleNamespace(config=types.SimpleNamespace(logging=cfg), save=lambda: saved.append(1)),
        cmd_registry=CommandRegistry(),
    )
    eng.cmd_registry.register("log", "log", lambda args: cmd_log(eng, args))
    return eng, cfg


@pytest.mark.parametrize("line,expected", [
    ("/log on my notes.md", "my notes.md"),
    ('/log on "my notes.md"', "my notes.md"),
    ("/log my notes.md", "my notes.md"),
    ("/log  logs/a  b.md", "logs/a  b.md"),
    ("/log on session.md", "session.md"),
])
def test_log_paths_with_spaces(line, expected):
    eng, cfg = _engine()
    assert asyncio.run(eng.cmd_registry.dispatch(line))
    assert eng.session_logger.filepath == expected
    assert cfg.filepath == expected and cfg.enabled and eng.session_logger.enabled


def test_log_off_and_on_default():
    eng, cfg = _engine()
    asyncio.run(eng.cmd_registry.dispatch("/log on"))
    assert eng.session_logger.enabled and eng.session_logger.filepath == "session.md"
    asyncio.run(eng.cmd_registry.dispatch("/log off"))
    assert not eng.session_logger.enabled


def test_logger_writes_file_with_space(tmp_path):
    from session_logger import SessionLogger
    path = tmp_path / "my dir" / "my log.md"
    lg = SessionLogger(str(path), enabled=True)
    lg.log_user_prompt("hi")
    assert "hi" in path.read_text(encoding="utf-8")


def test_log_completion_with_spaces(tmp_path, monkeypatch):
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit.document import Document
    from terminal_ui import MeshCompleter
    (tmp_path / "my notes.md").write_text("x")
    monkeypatch.chdir(tmp_path)
    comp = MeshCompleter(types.SimpleNamespace())
    got = [c.text for c in comp.get_completions(Document("/log on my n"), None)]
    assert "my notes.md" in got
    got = [c.text for c in comp.get_completions(Document("/log my n"), None)]
    assert "my notes.md" in got


def _run_keys(data: str):
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit import PromptSession
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    import terminal_ui

    with create_pipe_input() as inp:
        inp.send_text(data)
        session = PromptSession(
            input=inp, output=DummyOutput(), multiline=True,
            key_bindings=terminal_ui.build_prompt_key_bindings(),
        )
        return session.prompt()


@pytest.mark.parametrize("seq", ["\x1b\r", "\x1b[13;2u", "\x1b[27;2;13~"])
def test_newline_keys_insert_newline(seq):
    assert _run_keys(f"a{seq}b\r") == "a\nb"


@pytest.mark.parametrize("seq", ["\r", "\n", "\x1b[27;5;13~", "\x1b[27;6;13~"])
def test_other_enter_variants_submit(seq):
    assert _run_keys(f"ab{seq}") == "ab"
