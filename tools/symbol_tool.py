from typing import Dict, Any, Optional
from tools.base import BaseTool
import symbol_search


class SearchSymbolsTool(BaseTool):
    name = "search_symbols"
    description = (
        "Universal Tree-sitter codebase symbol search. Finds function, class, interface, and method "
        "definitions, signatures, line numbers, and docstrings across Python, JavaScript, TypeScript, "
        "Rust, Go, C/C++, Java, C#, PHP, and Ruby files without reading whole files."
    )
    is_proxied = True
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Symbol name or substring to search (e.g. 'compact_messages' or 'ToolRegistry')."
            },
            "kind": {
                "type": "string",
                "enum": ["class", "function", "method"],
                "description": "Optional symbol kind filter."
            }
        },
        "required": ["query"]
    }

    def __init__(self, config_mgr: Optional[Any] = None):
        self._config_mgr = config_mgr

    async def execute(self, query: str, kind: Optional[str] = None) -> Dict[str, Any]:
        if not symbol_search.symbol_indexer.symbol_index:
            symbol_search.symbol_indexer.load_cache(".")

        if symbol_search.symbol_indexer.is_indexing:
            await symbol_search.symbol_indexer.wait_for_indexing()
        elif not symbol_search.symbol_indexer.symbol_index:
            symbol_search.symbol_indexer.index_directory(".")
        
        limit_val = self._config_mgr.config.budgets.symbol if self._config_mgr else 30
        matches = symbol_search.symbol_indexer.search_symbols(query, kind=kind, limit=limit_val)
        return {
            "query": query,
            "count": len(matches),
            "matches": matches
        }
