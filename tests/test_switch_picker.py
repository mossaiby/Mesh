import asyncio
import types

import commands.model_commands as mc
from config import MeshConfig, ModelConfig, ProviderConfig


def _cfg():
    cfg = MeshConfig(active_model="zeta:b")
    cfg.providers = {
        "zeta": ProviderConfig(name="Zeta", base_url="http://z/v1", api_key_env="Z"),
        "alpha": ProviderConfig(name="Alpha", base_url="http://a/v1", api_key_env="A"),
    }
    def m(prov, mid, name):
        return ModelConfig(provider=prov, model_id=mid, name=name, context_window=8192)
    cfg.models = {
        "zeta:b": m("zeta", "b", "Bravo"),
        "zeta:a": m("zeta", "a", "Apple"),
        "alpha:z": m("alpha", "z", "Zulu"),
        "alpha:c": m("alpha", "c", "Charlie"),
    }
    return cfg


def test_sorted_helpers():
    cfg = _cfg()
    assert mc._sorted_provider_keys(cfg) == ["alpha", "zeta"]
    assert mc._sorted_model_keys(cfg) == ["zeta:a", "zeta:b", "alpha:c", "alpha:z"]  # Apple, Bravo, Charlie, Zulu
    assert mc._sorted_model_keys(cfg, "alpha") == ["alpha:c", "alpha:z"]
    assert mc._sorted_model_keys(cfg, "zeta") == ["zeta:a", "zeta:b"]


def test_switch_picks_provider_then_model(monkeypatch):
    cfg = _cfg()
    chosen = {}
    calls = []

    def fake_picker(items, title, initial_idx=0):
        calls.append((list(items), title, initial_idx))
        if len(calls) == 1:  # provider step: alphabetical, auto last
            assert items[0].startswith("Alpha") and items[1].startswith("Zeta")
            assert "Auto-Routing" in items[-1]
            return items[0]
        assert [i.split(" (")[0] for i in items] == ["Charlie", "Zulu"]
        return items[1]

    class Mgr:
        config = cfg
        def set_active_model(self, k):
            chosen["k"] = k
        def get_active_model_and_provider(self):
            return cfg.models[chosen["k"]], cfg.providers[cfg.models[chosen["k"]].provider]

    monkeypatch.setattr(mc, "_interactive_item_picker", fake_picker)
    asyncio.run(mc.cmd_switch(types.SimpleNamespace(config_mgr=Mgr()), []))
    assert chosen["k"] == "alpha:z"
    assert calls[0][2] == 1  # starts on the active model's provider (Zeta)


def test_switch_escape_returns_to_providers(monkeypatch):
    cfg = _cfg()
    state = {"n": 0}
    chosen = {}

    def fake_picker(items, title, initial_idx=0):
        state["n"] += 1
        if state["n"] == 1:
            return items[0]
        if state["n"] == 2:
            return None
        if state["n"] == 3:
            return items[1]
        return items[0]

    class Mgr:
        config = cfg
        def set_active_model(self, k):
            chosen["k"] = k
        def get_active_model_and_provider(self):
            return cfg.models[chosen["k"]], cfg.providers[cfg.models[chosen["k"]].provider]

    monkeypatch.setattr(mc, "_interactive_item_picker", fake_picker)
    asyncio.run(mc.cmd_switch(types.SimpleNamespace(config_mgr=Mgr()), []))
    assert chosen["k"] == "zeta:a"
