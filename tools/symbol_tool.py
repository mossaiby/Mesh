from typing import Dict, Any, Optional
from tools.base import BaseTool
import symbol_search


class SearchSymbolsTool(BaseTool):
    name = "search_symbols"
    description = (
        "Fast AST codebase symbol search. Finds function, class, and method definitions, "
        "signatures, line numbers, and docstrings across workspace Python files without "
        "reading entire files."
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
                "enum": ["class", "function", "async_function"],
                "description": "Optional symbol kind filter."
            }
        },
        "required": ["query"]
    }

    async def execute(self, query: str, kind: Optional[str] = None) -> Dict[str, Any]:
        if not symbol_search.symbol_indexer.symbol_index:
            indexed_count = symbol_search.symbol_indexer.index_directory(".")
        
        matches = symbol_search.symbol_indexer.search_symbols(query, kind=kind)
        return {
            "query": query,
            "count": len(matches),
            "matches": matches
        }