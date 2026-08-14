import os
import sys
import tempfile
import inspect
import asyncio
import pytest
from pathlib import Path
from typing import Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.permissions import PermissionManager
from tools.goal_tool import GoalTool
from tools.todo_tool import TodoTool
from tools.registry import ToolRegistry
from checkpoint import CheckpointManager


def pytest_configure(config):
    """Register custom markers to eliminate PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers", "asyncio: mark test function to run as an asyncio coroutine"
    )


def pytest_pyfunc_call(pyfuncitem):
    """
    Hook to automatically run `async def` test functions using Python's built-in
    asyncio.run() without requiring third-party plugins like pytest-asyncio.
    """
    testfunction = pyfuncitem.obj
    if inspect.iscoroutinefunction(testfunction):
        argnames = pyfuncitem._fixtureinfo.argnames
        param_dict = {
            arg: pyfuncitem.funcargs[arg]
            for arg in argnames
            if arg in pyfuncitem.funcargs
        }
        asyncio.run(testfunction(**param_dict))
        return True
    return None


class MockModelConfig:
    def __init__(self, name="Test Model", provider="openai", model_id="gpt-4o", context_window=128000):
        self.name = name
        self.provider = provider
        self.model_id = model_id
        self.context_window = context_window
        self.tags = ["test"]
        self.description = "Mock model"


class MockProviderConfig:
    def __init__(self, name="Mock Provider", base_url="https://api.openai.com/v1"):
        self.name = name
        self.base_url = base_url
        self.api_key_env = "OPENAI_API_KEY"
        self.default_headers = None

    @property
    def api_key(self) -> str:
        return "mock-api-key"


class MockMeshConfig:
    def __init__(self):
        self.active_model = "openai:gpt-4o"
        self.system_prompt = "You are Mesh."
        self.auto_compact = True
        self.auto_compact_threshold = 0.75
        self.max_delegation_depth = 2
        self.advisor_model = None
        self.guard_enabled = False
        self.guard_model = None
        self.guard_autonomy = "supervised"
        self.router_model = "openai:gpt-4o"
        self.network_proxy = None
        self.thinking = True
        self.effort = "medium"
        self.show_tokens = True
        self.show_cost = True
        self.show_statistics = True
        self.models = {"openai:gpt-4o": MockModelConfig()}
        self.providers = {"openai": MockProviderConfig()}

        class Obj:
            pass

        self.timeouts = Obj()
        self.timeouts.web = 15.0
        self.timeouts.shell = 30.0
        self.timeouts.mcp = 60.0
        self.timeouts.linter = 10.0
        self.timeouts.python = 10.0
        self.timeouts.api = 12.0

        self.budgets = Obj()
        self.budgets.web = 8000
        self.budgets.repo_map = 500
        self.budgets.dream = 12000
        self.budgets.git_diff = 4000
        self.budgets.symbol = 30

        self.turns = Obj()
        self.turns.agent = 6
        self.turns.engine = 10
        self.turns.loop = 5
        self.turns.depth = 2
        self.turns.branches = 3

        self.repair_settings = Obj()
        self.repair_settings.retries = 2
        self.repair_settings.delay = 0.1

        self.retry_settings = Obj()
        self.retry_settings.retries = 3
        self.retry_settings.initial_delay = 1.0
        self.retry_settings.max_delay = 30.0
        self.retry_settings.backoff_factor = 2.0
        self.retry_settings.jitter = True

        self.compaction_settings = Obj()
        self.compaction_settings.minkeep = 2

        self.logging = Obj()
        self.logging.enabled = False
        self.logging.filepath = "session.md"


class MockConfigManager:
    def __init__(self):
        self.config = MockMeshConfig()

    def get_model_and_provider(self, key: str):
        if key == "auto":
            raise KeyError("Active model is set to 'auto'.")
        if key not in self.config.models:
            raise KeyError(f"Model key '{key}' not found.")
        return self.config.models[key], self.config.providers["openai"]

    def get_active_model_and_provider(self):
        return self.get_model_and_provider(self.config.active_model)

    def set_active_model(self, key: str):
        self.config.active_model = key

    def save(self):
        pass


class MockMeshEngine:
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.config_mgr = MockConfigManager()
        self.permission_manager = PermissionManager()
        self.permission_manager.allowed_dirs = [temp_dir]
        self.tool_registry = ToolRegistry()
        self.goal_tool = GoalTool(on_change=lambda: None)
        self.todo_tool = TodoTool()
        self.tool_registry.register(self.goal_tool)
        self.tool_registry.register(self.todo_tool)
        self.checkpoint_mgr = CheckpointManager()
        self.current_mode = "build"
        self.tools_enabled = True
        self.debug_mode = False

        # Session Metrics
        self.session_prompt_tokens = 1500
        self.session_completion_tokens = 600
        self.session_cached_tokens = 250
        self.session_cost_usd = 0.0125
        self.messages = [
            {"role": "user", "content": "Hello Mesh"},
            {"role": "assistant", "content": "Hello! How can I help you today?"}
        ]

    def update_system_message(self, base_prompt: str = None):
        pass


@pytest.fixture
def temp_workspace():
    """Provides a temporary directory workspace and sets CWD to it."""
    orig_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        resolved = str(Path(tmp_dir).resolve())
        os.chdir(resolved)
        try:
            yield resolved
        finally:
            os.chdir(orig_cwd)


@pytest.fixture
def mock_engine(temp_workspace):
    """Provides an instantiated MockMeshEngine operating inside the temporary workspace."""
    return MockMeshEngine(temp_workspace)
