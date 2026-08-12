import ast
import os
from typing import Dict, Any, List, Optional, Tuple
from theme import console

try:
    import tree_sitter_languages
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


LANGUAGE_EXTENSIONS: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".java": "java",
    ".cs": "c_sharp",
    ".php": "php",
    ".rb": "ruby"
}


class SymbolIndexer:
    """
    Parses AST of codebase files across workspace directories using Tree-sitter,
    building an in-memory index of classes, functions, interfaces, methods, and docstrings.
    """
    def __init__(self):
        self.symbol_index: List[Dict[str, Any]] = []

    def index_directory(self, root_dir: str = ".") -> int:
        """Walks root_dir and indexes codebase symbols via Tree-sitter or AST parsing."""
        self.symbol_index.clear()
        indexed_files = 0

        for root, _, files in os.walk(root_dir):
            if any(p in root for p in [".git", "__pycache__", ".venv", "venv", "custom_tools", "node_modules", "target", "build"]):
                continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in LANGUAGE_EXTENSIONS:
                    filepath = os.path.join(root, file)
                    lang = LANGUAGE_EXTENSIONS[ext]
                    try:
                        success = self._parse_file_with_treesitter(filepath, lang)
                        if not success and ext == ".py":
                            self._parse_python_with_ast(filepath)
                        indexed_files += 1
                    except Exception:
                        pass
        return indexed_files

    def _parse_file_with_treesitter(self, filepath: str, lang: str) -> bool:
        """Parses source file using Tree-sitter polyglot AST nodes."""
        if not TREE_SITTER_AVAILABLE:
            return False

        try:
            parser = tree_sitter_languages.get_parser(lang)
            with open(filepath, "rb") as f:
                code_bytes = f.read()

            tree = parser.parse(code_bytes)
            rel_path = os.path.relpath(filepath)

            self._traverse_tree_nodes(tree.root_node, code_bytes, rel_path)
            return True
        except Exception:
            return False

    def _traverse_tree_nodes(self, node, code_bytes: bytes, rel_path: str):
        """Recursively traverses Tree-sitter AST nodes to extract symbol signatures."""
        node_type = node.type

        if node_type in (
            "function_declaration", "function_definition", "method_definition",
            "class_declaration", "class_definition", "interface_declaration",
            "struct_item", "impl_item", "type_alias_declaration"
        ):
            name_node = node.child_by_field_name("name")
            if name_node:
                symbol_name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                line_no = node.start_point[0] + 1
                
                first_line = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").splitlines()[0]

                kind = "function"
                if "class" in node_type or "struct" in node_type or "interface" in node_type:
                    kind = "class"
                elif "method" in node_type:
                    kind = "method"

                self.symbol_index.append({
                    "name": symbol_name,
                    "kind": kind,
                    "signature": first_line[:120].strip(),
                    "filepath": rel_path,
                    "line": line_no,
                    "docstring": ""
                })

        for child in node.children:
            self._traverse_tree_nodes(child, code_bytes, rel_path)

    def _parse_python_with_ast(self, filepath: str):
        """Fallback Python AST parser when Tree-sitter is unavailable."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
            tree = ast.parse(code, filename=filepath)
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
        except Exception:
            pass

    def search_symbols(self, query: str, kind: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        """Searches indexed codebase symbols matching query and optional kind filter."""
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

        return matches[:limit]


# Global symbol indexer instance
symbol_indexer = SymbolIndexer()
