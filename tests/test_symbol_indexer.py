import os
import json
import pytest
from symbol_search import SymbolIndexer


def test_symbol_indexer_disk_cache(temp_workspace):
    indexer = SymbolIndexer()

    # Create dummy source files
    src_file = os.path.join(temp_workspace, "service.py")
    with open(src_file, "w", encoding="utf-8") as f:
        f.write("def calculate_metrics(values):\n    return sum(values)\n\nclass MetricsAggregator:\n    pass\n")

    # Index directory and verify cache creation
    count = indexer.index_directory(temp_workspace)
    assert count == 1
    assert len(indexer.symbol_index) == 2

    cache_path = os.path.join(temp_workspace, ".mesh", "symbols.cache.json")
    assert os.path.exists(cache_path)

    with open(cache_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "service.py" in data["files"]
    assert len(data["files"]["service.py"]["symbols"]) == 2

    # Instantiate fresh indexer and test fast load_cache
    fresh_indexer = SymbolIndexer()
    loaded = fresh_indexer.load_cache(temp_workspace)
    assert loaded is True
    assert len(fresh_indexer.symbol_index) == 2

    matches = fresh_indexer.search_symbols("calculate_metrics")
    assert len(matches) == 1
    assert matches[0]["name"] == "calculate_metrics"


def test_symbol_indexer_hot_update_and_remove(temp_workspace):
    indexer = SymbolIndexer()

    file_a = os.path.join(temp_workspace, "a.py")
    with open(file_a, "w", encoding="utf-8") as f:
        f.write("def initial_func(): pass\n")

    indexer.index_directory(temp_workspace)
    assert any(s["name"] == "initial_func" for s in indexer.symbol_index)

    # Hot update file
    with open(file_a, "w", encoding="utf-8") as f:
        f.write("def updated_func(): pass\n")

    indexer.index_file(file_a, root_dir=temp_workspace)
    assert any(s["name"] == "updated_func" for s in indexer.symbol_index)
    assert not any(s["name"] == "initial_func" for s in indexer.symbol_index)

    # Hot remove file
    os.remove(file_a)
    indexer.remove_file(file_a, root_dir=temp_workspace)
    assert len(indexer.symbol_index) == 0


@pytest.mark.asyncio
async def test_symbol_indexer_background_task(temp_workspace):
    indexer = SymbolIndexer()

    file_b = os.path.join(temp_workspace, "worker.py")
    with open(file_b, "w", encoding="utf-8") as f:
        f.write("async def process_task(task_id):\n    pass\n")

    task = indexer.start_background_indexing(temp_workspace)
    assert task is not None

    count = await task
    assert count == 1
    assert len(indexer.symbol_index) == 1
    assert indexer.symbol_index[0]["name"] == "process_task"
