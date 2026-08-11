import ast
import os
from typing import Dict, Any, List, Optional


class SymbolIndexer:
    """
    Parses AST of Python files across workspace directories, building an
    in-memory index of classes, functions, methods, and docstrings.
    """
    def __init__(self):
        self.symbol_index: List[Dict[str, Any]] = []

    def index_directory(self, root_dir: str = ".") -> int:
        """Walks root_dir and indexes Python symbols via AST parsing."""
        self.symbol_index.clear()
        indexed_files = 0

        for root, _, files in os.walk(root_dir):
            if any(p in root for p in [".git", "__pycache__", ".venv", "venv", "custom_tools"]):
                continue
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                            code = f.read()
                        tree = ast.parse(code, filename=filepath)
                        self._extract_symbols_from_ast(tree, filepath)
                        indexed_files += 1
                    except Exception:
                        pass
        return indexed_files

    def _extract_symbols_from_ast(self, tree: ast.AST, filepath: str) -> None:
        rel_path = os.path.relpath(filepath)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                sig = f"{node.name}({', '.join(args)})"
                docstring = ast.get_docstring(node) or ""
                self.symbol_index.append({
                    "name": node.name,
                    "kind": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                    "signature": sig,
                    "filepath": rel_path,
                    "line": node.lineno,
                    "docstring": docstring[:200]
                })

            elif isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node) or ""
                bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
                base_str = f"({', '.join(bases)})" if bases else ""
                self.symbol_index.append({
                    "name": node.name,
                    "kind": "class",
                    "signature": f"class {node.name}{base_str}",
                    "filepath": rel_path,
                    "line": node.lineno,
                    "docstring": docstring[:200]
                })

    def search_symbols(self, query: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches indexed symbols matching query and optional kind (class/function)."""
        query_lower = query.lower().strip()
        matches = []

        for item in self.symbol_index:
            if kind and kind.lower() not in item["kind"]:
                continue

            if (
                query_lower in item["name"].lower()
                or query_lower in item["signature"].lower()
                or query_lower in item["docstring"].lower()
            ):
                matches.append(item)

        return matches[:30]


# Global symbol indexer instance
symbol_indexer = SymbolIndexer()