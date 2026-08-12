import json
import os
from typing import Dict, Optional, Tuple, List
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    default_headers: Optional[Dict[str, str]] = None

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "dummy-key-for-local-providers")


class ModelConfig(BaseModel):
    name: str
    provider: str
    model_id: str
    context_window: int = 8192
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class MeshConfig(BaseModel):
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
    # Metrics display toggles
    show_tokens: bool = True
    show_cost: bool = True
    show_statistics: bool = True
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)


class ConfigManager:
    def __init__(self, filepath: str = "models.json"):
        self.filepath = filepath
        self.config: MeshConfig = self.load()

    def load(self) -> MeshConfig:
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Configuration file {self.filepath} not found.")
        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MeshConfig(**data)

    def save(self) -> None:
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(self.config.model_dump_json(indent=2))

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
                raise ValueError("Auto-routing mode is active, but 'router_model' is not configured in models.json.")
            return self.get_model_and_provider(self.config.router_model)
        return self.get_model_and_provider(self.config.active_model)

    def set_active_model(self, key: str) -> None:
        if key == "auto":
            if not self.config.router_model:
                raise ValueError("Cannot set active_model to 'auto': 'router_model' is not configured in models.json.")
            if self.config.router_model not in self.config.models:
                raise ValueError(f"Configured router model '{self.config.router_model}' does not exist in models.json.")
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
        """Adds or updates a model entry in models.json."""
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
