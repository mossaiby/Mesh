import os
import pytest
from config import ConfigManager, MeshConfig


def test_config_manager_add_and_remove_provider(temp_workspace):
    cfg_file = os.path.join(temp_workspace, "config.json")
    initial_config = MeshConfig(
        active_model="openai:gpt-4o",
        system_prompt="Test assistant"
    )
    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(initial_config.model_dump_json(indent=2, by_alias=True))

    config_mgr = ConfigManager(cfg_file)

    # 1. Add new provider
    config_mgr.add_provider(
        key="deepseek",
        name="DeepSeek Official",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY"
    )

    assert "deepseek" in config_mgr.config.providers
    assert config_mgr.config.providers["deepseek"].base_url == "https://api.deepseek.com/v1"

    # Add a model bound to this provider
    config_mgr.add_model(
        key="deepseek:deepseek-chat",
        provider="deepseek",
        model_id="deepseek-chat",
        name="DeepSeek Chat",
        context_window=65536
    )
    assert "deepseek:deepseek-chat" in config_mgr.config.models

    # 2. Add and remove header
    config_mgr.set_provider_header("deepseek", "X-Custom-Header", "MeshTest")
    assert config_mgr.config.providers["deepseek"].default_headers.get("X-Custom-Header") == "MeshTest"

    config_mgr.remove_provider_header("deepseek", "X-Custom-Header")
    assert config_mgr.config.providers["deepseek"].default_headers is None

    # 3. Remove provider and verify associated model pruning
    success, removed_models = config_mgr.remove_provider("deepseek", remove_associated_models=True)
    assert success is True
    assert "deepseek" not in config_mgr.config.providers
    assert "deepseek:deepseek-chat" in removed_models
    assert "deepseek:deepseek-chat" not in config_mgr.config.models
