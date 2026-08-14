import json
import os
from typing import Dict, Optional, Tuple, List
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

    web: float = 15.0
    shell: float = 30.0
    mcp: float = 60.0
    linter: float = 10.0
    python: float = 10.0
    api: float = 12.0


class BudgetsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    web: int = 8000
    repo_map: int = Field(default=500, alias="repo-map")
    dream: int = 12000
    git_diff: int = Field(default=4000, alias="git-diff")
    symbol: int = 30


class TurnsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    agent: int = 6
    engine: int = 10
    loop: int = 5
    depth: int = 2
    branches: int = 3


class RepairConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    retries: int = 2
    delay: float = 0.75


class RetryConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    retries: int = 3
    initial_delay: float = Field(default=1.0, alias="initial-delay")
    max_delay: float = Field(default=30.0, alias="max-delay")
    backoff_factor: float = Field(default=2.0, alias="backoff-factor")
    jitter: bool = True


class CompactionSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    minkeep: int = 2


class LoggingConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = False
    filepath: str = "session.md"


class ProviderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    default_headers: Optional[Dict[str, str]] = None

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "dummy-key-for-local-providers")


class ModelConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    provider: str
    model_id: str
    context_window: int = 8192
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class MeshConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    active_model: str
    system_prompt: str = "You are a helpful text-based AI assistant running inside Mesh, an interactive terminal CLI."
    auto_compact: bool = True
    auto_compact_threshold: float = 0.75
    # How many levels deep delegate_task may recurse
    max_delegation_depth: int = 2
    # Optional dedicated models for reasoning advisor, safety guard, and model router
    advisor_model: Optional[str] = None
    guard_enabled: bool = True
    guard_model: Optional[str] = None
    guard_autonomy: str = "supervised"
    router_model: Optional[str] = None
    # Global network proxy URL
    network_proxy: Optional[str] = None
    # Extended thinking / reasoning controls
    thinking: bool = True
    effort: str = "medium"
    # Metrics display toggles
    show_tokens: bool = True
    show_cost: bool = True
    show_statistics: bool = True

    # Categorized system parameters
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    turns: TurnsConfig = Field(default_factory=TurnsConfig)
    repair_settings: RepairConfig = Field(default_factory=RepairConfig)
    retry_settings: RetryConfig = Field(default_factory=RetryConfig)
    compaction_settings: CompactionSettings = Field(default_factory=CompactionSettings)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)


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
        return cfg

    def save(self) -> None:
        self.config.max_delegation_depth = self.config.turns.depth
        apply_network_proxy(self.config.network_proxy)
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(self.config.model_dump_json(indent=2, by_alias=True))

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
