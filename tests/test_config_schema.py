import json
import os
from config import generate_config_schema, MeshConfig, ConfigManager


def test_generate_config_schema(temp_workspace):
    schema_file = os.path.join(temp_workspace, "config.schema.json")
    schema = generate_config_schema(schema_file)

    assert os.path.exists(schema_file)
    assert schema["title"] == "Mesh Configuration Schema"
    assert "$schema" in schema
    assert "properties" in schema
    assert "active_model" in schema["properties"]
    assert "retry_settings" in schema["properties"]
    assert "timeouts" in schema["properties"]

    # Verify JSON roundtrip
    with open(schema_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["type"] == "object"
    assert "$defs" in loaded
    assert "RetryConfig" in loaded["$defs"]
    assert "ProviderConfig" in loaded["$defs"]
    assert "ModelConfig" in loaded["$defs"]


def test_mesh_config_schema_field_roundtrip(temp_workspace):
    cfg_file = os.path.join(temp_workspace, "config.json")
    schema_file = os.path.join(temp_workspace, "config.schema.json")

    # Create initial configuration file
    initial_config = MeshConfig(
        active_model="openai:gpt-4o",
        system_prompt="Test assistant"
    )
    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(initial_config.model_dump_json(indent=2, by_alias=True))

    # Load and save via real ConfigManager
    config_mgr = ConfigManager(cfg_file)
    config_mgr.save()

    assert os.path.exists(cfg_file)
    assert os.path.exists(schema_file)

    with open(cfg_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("$schema") == "./config.schema.json"
