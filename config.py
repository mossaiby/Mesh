import json
import os
from typing import Dict, Optional, Tuple, List, Any
from pydantic import BaseModel, Field, ConfigDict


def apply_network_proxy(proxy_url: Optional[str]) -> None:
    """Sets or clears HTTP/HTTPS/ALL_PROXY environment variables."""
    if proxy_url and proxy_url.strip():
        url = proxy_url.strip()
        os.environ["HTTP_PROXY"] = url
        os.environ["HTTPS_PROXY"] = url
        os.environ["ALL_PROXY"] = url
    else:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(k, None)


class TimeoutsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    web: float = Field(default=15.0, description="Web search and fetch HTTP timeout in seconds.")
    shell: float = Field(default=30.0, description="Native shell command execution timeout in seconds.")
    mcp: float = Field(default=60.0, description="Model Context Protocol (MCP) client request timeout in seconds.")
    linter: float = Field(default=10.0, description="Post-edit linter hook execution timeout in seconds.")
    python: float = Field(default=10.0, description="Direct Python snippet execution tool timeout in seconds.")
    api: float = Field(default=12.0, description="Provider model discovery API call timeout in seconds.")


class BudgetsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    web: int = Field(default=8000, description="Maximum character budget for fetched web pages.")
    repo_map: int = Field(default=500, alias="repo-map", description="Token budget for repository architecture map generation.")
    dream: int = Field(default=12000, description="Maximum character budget for conversation transcript during /dream.")
    git_diff: int = Field(default=4000, alias="git-diff", description="Character budget for Git diff during commit message synthesis.")
    symbol: int = Field(default=30, description="Maximum symbol search matches returned by search_symbols.")


def default_timeout(name: str) -> float:
    """
    Returns the canonical default for a TimeoutsConfig field (e.g. "shell", "web", "mcp").
    Call sites that need a fallback for when no ConfigManager is available should use this
    instead of re-typing the literal, so TimeoutsConfig stays the single source of truth.
    """
    return TimeoutsConfig.model_fields[name].default


def default_budget(name: str) -> int:
    """Same as default_timeout(), but for BudgetsConfig fields (e.g. "web", "symbol")."""
    return BudgetsConfig.model_fields[name].default


class TurnsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    agent: int = Field(default=6, description="Default maximum tool turns per autonomous sub-agent.")
    engine: int = Field(default=10, description="Maximum assistant turn loops per prompt turn.")
    loop: int = Field(default=5, description="Maximum test/fix iterations for /loop.")
    depth: int = Field(default=2, description="Maximum delegation recursion depth.")
    branches: int = Field(default=3, description="Default parallel exploration strategy branches for /agent explore.")


class RepairConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    retries: int = Field(default=2, description="Mechanical retries for transient tool errors.")
    delay: float = Field(default=0.75, description="Mechanical retry delay in seconds.")


class RetryConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    retries: int = Field(default=3, description="Maximum provider API request retry attempts for rate limits and transient errors.")
    initial_delay: float = Field(default=1.0, alias="initial-delay", description="Initial retry delay in seconds.")
    max_delay: float = Field(default=30.0, alias="max-delay", description="Maximum backoff delay ceiling in seconds.")
    backoff_factor: float = Field(default=2.0, alias="backoff-factor", description="Exponential backoff multiplier factor.")
    jitter: bool = Field(default=True, description="Apply randomized jitter to retry backoff delay to prevent thundering herd.")


class CompactionSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    minkeep: int = Field(default=2, description="Minimum recent messages to keep uncompacted during context compaction.")


class LoggingConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = Field(default=False, description="Whether Markdown session logging is enabled.")
    filepath: str = Field(default="session.md", description="Filepath for Markdown session log file.")


class ProviderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Display name of the model provider.")
    base_url: str = Field(description="REST API base URL endpoint (e.g. https://api.openai.com/v1).")
    api_key_env: str = Field(default="OPENAI_API_KEY", description="Environment variable name storing the provider API key.")
    default_headers: Optional[Dict[str, str]] = Field(default=None, description="Optional custom HTTP headers sent with every request.")

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "dummy-key-for-local-providers")


class ModelConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Human-readable display name for the model.")
    provider: str = Field(description="Provider key matching a configured provider in providers.")
    model_id: str = Field(description="Exact provider model identifier (e.g. gpt-4o, claude-3-7-sonnet-20250219).")
    context_window: int = Field(default=8192, description="Maximum token context window size for the model.")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. reasoning, coding, fast, free, router, guard).")
    description: Optional[str] = Field(default=None, description="Detailed description of model capabilities and intended use cases.")


class MeshConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    schema_url: Optional[str] = Field(
        default="./config.schema.json",
        alias="$schema",
        description="JSON Schema URI for IDE validation and autocompletion in config.json."
    )
    active_model: str = Field(
        description="Active model key (e.g. anthropic:claude-3-7-sonnet-20250219) or 'auto' for dynamic prompt auto-routing."
    )
    system_prompt: str = Field(
        default="You are a helpful text-based AI assistant running inside Mesh, an interactive terminal CLI.",
        description="Base system instructions injected at the start of conversation turns."
    )
    auto_compact: bool = Field(
        default=True,
        description="Automatically summarize older conversation history when context window threshold is reached."
    )
    auto_compact_threshold: float = Field(
        default=0.75,
        description="Context window usage ratio (0.01 to 1.0) that triggers automatic context compaction."
    )
    max_delegation_depth: int = Field(
        default=2,
        description="Maximum recursion depth for autonomous sub-agent task delegation."
    )
    advisor_model: Optional[str] = Field(
        default=None,
        description="Dedicated model key to consult for second opinions during /agent advisor (defaults to active model)."
    )
    guard_enabled: bool = Field(
        default=True,
        description="Whether the Safety Guard risk assessment is enabled for mutating tool calls."
    )
    guard_model: Optional[str] = Field(
        default=None,
        description="Dedicated model key used for Safety Guard risk assessment."
    )
    guard_autonomy: str = Field(
        default="supervised",
        description="Autonomy mode for Safety Guard: 'supervised' (interactive approval) or 'autonomous' (auto-approve low/medium risk)."
    )
    router_model: Optional[str] = Field(
        default=None,
        description="Dedicated model key used for prompt auto-routing when active_model is set to 'auto'."
    )
    network_proxy: Optional[str] = Field(
        default=None,
        description="Global network HTTP/HTTPS/SOCKS proxy URL (e.g. socks5h://localhost:1080)."
    )
    thinking: bool = Field(
        default=True,
        description="Whether extended thinking/reasoning mode is enabled for supported models."
    )
    effort: str = Field(
        default="medium",
        description="Reasoning effort level for extended thinking models ('low', 'medium', 'high')."
    )
    show_tokens: bool = Field(
        default=True,
        description="Display turn and cached token count metrics in CLI response footers."
    )
    show_cost: bool = Field(
        default=True,
        description="Display turn and session USD cost metrics in CLI response footers."
    )
    show_statistics: bool = Field(
        default=True,
        description="Display TTFT (time to first token) and tok/s performance statistics in CLI response footers."
    )

    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig, description="HTTP and subprocess execution timeouts.")
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig, description="Token and character output budgets for tools.")
    turns: TurnsConfig = Field(default_factory=TurnsConfig, description="Maximum turn limits for agents, engine loops, and exploration.")
    repair_settings: RepairConfig = Field(default_factory=RepairConfig, description="Tool repair and transient retry settings.")
    retry_settings: RetryConfig = Field(default_factory=RetryConfig, description="Provider API exponential backoff and retry settings.")
    compaction_settings: CompactionSettings = Field(default_factory=CompactionSettings, description="Context compaction retention parameters.")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Markdown session logging configuration.")

    providers: Dict[str, ProviderConfig] = Field(default_factory=dict, description="Configured LLM providers and endpoints.")
    models: Dict[str, ModelConfig] = Field(default_factory=dict, description="Configured model registry with context windows and provider bindings.")


def generate_config_schema(filepath: str = "config.schema.json") -> Dict[str, Any]:
    """
    Generates a full JSON Schema Draft 2020-12 from the MeshConfig Pydantic model
    and saves it to filepath for IDE validation and autocompletion.
    """
    schema = MeshConfig.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Mesh Configuration Schema"
    schema["description"] = "JSON Schema for Mesh AI CLI harness configuration (config.json). Provides autocomplete and validation in VS Code, Cursor, and other IDEs."

    try:
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
    except Exception:
        pass

    return schema


class ConfigManager:
    def __init__(self, filepath: str = "config.json"):
        self.filepath = filepath
        self.config: MeshConfig = self.load()

    def load(self) -> MeshConfig:
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Configuration file '{self.filepath}' not found.")

        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        cfg = MeshConfig(**data)
        if cfg.turns.depth != cfg.max_delegation_depth:
            cfg.turns.depth = cfg.max_delegation_depth
        apply_network_proxy(cfg.network_proxy)

        # Auto-generate or update config.schema.json alongside config.json
        schema_path = os.path.join(os.path.dirname(self.filepath) or ".", "config.schema.json")
        if not os.path.exists(schema_path):
            generate_config_schema(schema_path)

        return cfg

    def save(self) -> None:
        self.config.max_delegation_depth = self.config.turns.depth
        apply_network_proxy(self.config.network_proxy)
        if not getattr(self.config, "schema_url", None):
            self.config.schema_url = "./config.schema.json"

        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(self.config.model_dump_json(indent=2, by_alias=True))

        schema_path = os.path.join(os.path.dirname(self.filepath) or ".", "config.schema.json")
        generate_config_schema(schema_path)

    def get_model_and_provider(self, key: str) -> Tuple[ModelConfig, ProviderConfig]:
        if key == "auto":
            raise KeyError("Active model is set to 'auto'. Specific model routing occurs per prompt.")

        if key not in self.config.models:
            raise KeyError(f"Model key '{key}' not found in models configuration.")

        model_cfg = self.config.models[key]

        if model_cfg.provider not in self.config.providers:
            raise KeyError(f"Provider '{model_cfg.provider}' referenced by '{key}' not found in providers configuration.")

        provider_cfg = self.config.providers[model_cfg.provider]
        return model_cfg, provider_cfg

    def get_active_model_and_provider(self) -> Tuple[ModelConfig, ProviderConfig]:
        if self.config.active_model == "auto":
            if not self.config.router_model:
                raise ValueError("Auto-routing mode is active, but 'router_model' is not configured in config.json.")
            return self.get_model_and_provider(self.config.router_model)
        return self.get_model_and_provider(self.config.active_model)

    def set_active_model(self, key: str) -> None:
        if key == "auto":
            if not self.config.router_model:
                raise ValueError("Cannot set active_model to 'auto': 'router_model' is not configured in config.json.")
            if self.config.router_model not in self.config.models:
                raise ValueError(f"Configured router model '{self.config.router_model}' does not exist in config.json.")
            self.config.active_model = "auto"
            self.save()
            return

        if key not in self.config.models:
            raise ValueError(f"Model key '{key}' does not exist.")
        self.config.active_model = key
        self.save()

    def add_provider(
        self,
        key: str,
        name: str,
        base_url: str,
        api_key_env: str = "OPENAI_API_KEY",
        default_headers: Optional[Dict[str, str]] = None
    ) -> None:
        """Adds or updates a provider endpoint configuration and persists to config.json."""
        provider_cfg = ProviderConfig(
            name=name,
            base_url=base_url,
            api_key_env=api_key_env,
            default_headers=default_headers
        )
        self.config.providers[key] = provider_cfg
        self.save()

    def remove_provider(self, key: str, remove_associated_models: bool = True) -> Tuple[bool, List[str]]:
        """Removes a provider endpoint and optionally prunes models associated with it."""
        if key not in self.config.providers:
            return False, []

        del self.config.providers[key]

        removed_models = []
        if remove_associated_models:
            models_to_remove = [
                m_key for m_key, m_cfg in self.config.models.items()
                if m_cfg.provider == key
            ]
            for m_key in models_to_remove:
                del self.config.models[m_key]
                removed_models.append(m_key)

        self.save()
        return True, removed_models

    def set_provider_header(self, key: str, header_name: str, header_val: str) -> None:
        """Sets a default HTTP header on the specified provider."""
        if key not in self.config.providers:
            raise KeyError(f"Provider '{key}' not found in configuration.")

        p_cfg = self.config.providers[key]
        if p_cfg.default_headers is None:
            p_cfg.default_headers = {}
        p_cfg.default_headers[header_name] = header_val
        self.save()

    def remove_provider_header(self, key: str, header_name: str) -> None:
        """Removes a custom header from the specified provider."""
        if key not in self.config.providers:
            raise KeyError(f"Provider '{key}' not found in configuration.")

        p_cfg = self.config.providers[key]
        if p_cfg.default_headers and header_name in p_cfg.default_headers:
            del p_cfg.default_headers[header_name]
            if not p_cfg.default_headers:
                p_cfg.default_headers = None
            self.save()

    def add_model(
        self,
        key: str,
        provider: str,
        model_id: str,
        name: Optional[str] = None,
        context_window: int = 8192,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> None:
        if provider not in self.config.providers:
            raise KeyError(f"Provider '{provider}' not found in providers configuration.")

        display_name = name or model_id.split("/")[-1].replace("-", " ").title()
        model_cfg = ModelConfig(
            name=display_name,
            provider=provider,
            model_id=model_id,
            context_window=context_window,
            tags=tags or [],
            description=description
        )
        self.config.models[key] = model_cfg
        self.save()

    def remove_model(self, key: str) -> bool:
        """Removes a model from configuration and resets active/router/guard bindings if needed."""
        if key not in self.config.models:
            return False

        del self.config.models[key]

        # Reset active/router/guard/advisor model references if they pointed to the removed model
        if self.config.active_model == key:
            remaining_keys = list(self.config.models.keys())
            self.config.active_model = remaining_keys[0] if remaining_keys else "auto"

        if self.config.router_model == key:
            self.config.router_model = None

        if self.config.guard_model == key:
            self.config.guard_model = None

        if self.config.advisor_model == key:
            self.config.advisor_model = None

        self.save()
        return True
