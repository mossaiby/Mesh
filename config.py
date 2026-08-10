import json
import os
from typing import Dict, Optional, Tuple
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


class MeshConfig(BaseModel):
    active_model: str
    system_prompt: str = "You are a helpful text-based AI assistant running inside Mesh, an interactive terminal CLI."
    auto_compact: bool = True
    auto_compact_threshold: float = 0.75
    # How many levels deep delegate_task may recurse (a sub-agent spawning its
    # own sub-agents). Depth 1 = the main agent's direct sub-agent; depth 2
    # = that sub-agent delegating further, etc. 2 is a meaningful default:
    # enough for a sub-agent to genuinely split a task into independent
    # pieces and hand those off too, without allowing runaway/unbounded
    # recursive chains. User-adjustable via /delegate depth <n>.
    max_delegation_depth: int = 2
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

    def get_active_model_and_provider(self) -> Tuple[ModelConfig, ProviderConfig]:
        active_key = self.config.active_model
        if active_key not in self.config.models:
            raise KeyError(f"Active model key '{active_key}' not found in models configuration.")
        
        model_cfg = self.config.models[active_key]
        
        if model_cfg.provider not in self.config.providers:
            raise KeyError(f"Provider '{model_cfg.provider}' referenced by '{active_key}' not found in providers configuration.")
        
        provider_cfg = self.config.providers[model_cfg.provider]
        return model_cfg, provider_cfg

    def set_active_model(self, key: str) -> None:
        if key not in self.config.models:
            raise ValueError(f"Model key '{key}' does not exist.")
        self.config.active_model = key
        self.save()