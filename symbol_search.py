import ast
import importlib
import json
import os
import time
import asyncio
import threading
from typing import Dict, Any, List, Optional, Tuple, Callable
from theme import console


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

LANGUAGE_MODULE_NAMES: Dict[str, str] = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "rust": "tree_sitter_rust",
    "go": "tree_sitter_go",
    "cpp": "tree_sitter_cpp",
    "c": "tree_sitter_c",
    "java": "tree_sitter_java",
    "c_sharp": "tree_sitter_c_sharp",
    "php": "tree_sitter_php",
    "ruby": "tree_sitter_ruby"
}

PARSER_CACHE: Dict[str, Any] = {}

CACHE_DIR = ".mesh"
CACHE_FILE = "symbols.cache.json"
CACHE_VERSION = 1

IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "custom_tools",
    "node_modules", "target", "build", ".mesh", "dist", ".tox",
    ".pytest_cache", ".hypothesis"
})


def get_tree_sitter_parser(lang_name: str) -> Optional[Any]:
    """
    Dynamically loads and returns a Tree-sitter Parser for the specified language.
    Supports modern official `tree-sitter-<lang>` PyPI packages (Python 3.10-3.14+)
    and falls back to legacy `tree-sitter-languages` if present.
    """
    if lang_name in PARSER_CACHE:
        return PARSER_CACHE[lang_name]

    # 1. Try modern individual tree-sitter language packages (e.g. tree_sitter_python)
    mod_name = LANGUAGE_MODULE_NAMES.get(lang_name)
    if mod_name:
        try:
            mod = importlib.import_module(mod_name)
            from tree_sitter import Language, Parser
            lang_obj = Language(mod.language())
            try:
                parser = Parser(lang_obj)
            except Exception:
                parser = Parser()
                parser.language = lang_obj
            PARSER_CACHE[lang_name] = parser
            return parser
        except Exception:
            pass

    # 2. Legacy fallback to tree_sitter_languages if installed
    try:
        import tree_sitter_languages
        parser = tree_sitter_languages.get_parser(lang_name)
        PARSER_CACHE[lang_name] = parser
        return parser
    except Exception:
        pass

    PARSER_CACHE[lang_name] = None
    return None


class SymbolIndexer:
    """
    Parses AST of codebase files across workspace directories using Tree-sitter,
    building an in-memory index of classes, functions, interfaces, methods, and docstrings
    for Python, JavaScript, TypeScript, Rust, Go, C/C++, Java, C#, PHP, and Ruby.
    Supports persistent disk caching in .mesh/symbols.cache.json and background non-blocking indexing.
    """
    def __init__(self):
        self.symbol_index: List[Dict[str, Any]] = []
        self.file_cache: Dict[str, Dict[str, Any]] = {}
        self.is_indexing: bool = False
        self.last_indexed_at: Optional[float] = None
        self._indexing_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()

    def get_cache_path(self, root_dir: str = ".") -> str:
        """Returns the full path to .mesh/symbols.cache.json for the given root directory."""
        return os.path.join(root_dir, CACHE_DIR, CACHE_FILE)

    def load_cache(self, root_dir: str = ".") -> bool:
        """Loads disk cache from .mesh/symbols.cache.json if present and valid."""
        cache_path = self.get_cache_path(root_dir)
        if not os.path.exists(cache_path):
            return False

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("version") == CACHE_VERSION and isinstance(data.get("files"), dict):
                with self._lock:
                    self.file_cache = data["files"]
                    self.last_indexed_at = data.get("updated_at")
                    self._rebuild_index_locked()
                return True
        except Exception:
            pass

        return False

    def save_cache(self, root_dir: str = ".") -> bool:
        """Saves current symbol index and file metadata to .mesh/symbols.cache.json."""
        cache_path = self.get_cache_path(root_dir)
        cache_dir = os.path.dirname(cache_path)

        try:
            os.makedirs(cache_dir, exist_ok=True)
            with self._lock:
                data = {
                    "version": CACHE_VERSION,
                    "updated_at": time.time(),
                    "file_count": len(self.file_cache),
                    "symbol_count": len(self.symbol_index),
                    "files": self.file_cache
                }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    def _rebuild_index_locked(self):
        """Rebuilds self.symbol_index from self.file_cache (assumes lock is held)."""
        rebuilt = []
        for file_info in self.file_cache.values():
            rebuilt.extend(file_info.get("symbols", []))
        self.symbol_index = rebuilt

    def parse_file_symbols(self, filepath: str, root_dir: str = ".") -> List[Dict[str, Any]]:
        """Parses AST of a single source file and returns the list of extracted symbol dicts."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in LANGUAGE_EXTENSIONS:
            return []

        rel_path = os.path.relpath(filepath, root_dir).replace("\\", "/")
        lang = LANGUAGE_EXTENSIONS[ext]

        symbols = self._parse_file_with_treesitter(filepath, lang, rel_path)
        if not symbols and ext == ".py":
            symbols = self._parse_python_with_ast(filepath, rel_path)

        return symbols

    def _parse_file_with_treesitter(self, filepath: str, lang: str, rel_path: str) -> List[Dict[str, Any]]:
        """Parses source file using Tree-sitter polyglot AST nodes."""
        parser = get_tree_sitter_parser(lang)
        if not parser:
            return []

        try:
            with open(filepath, "rb") as f:
                code_bytes = f.read()

            tree = parser.parse(code_bytes)
            symbols: List[Dict[str, Any]] = []
            self._traverse_tree_nodes(tree.root_node, code_bytes, rel_path, symbols)
            return symbols
        except Exception:
            return []

    def _traverse_tree_nodes(self, node, code_bytes: bytes, rel_path: str, symbols: List[Dict[str, Any]]):
        """Recursively traverses Tree-sitter AST nodes to extract symbol signatures."""
        node_type = node.type

        if node_type in (
            "function_declaration", "function_definition", "method_definition", "method_declaration",
            "class_declaration", "class_definition", "interface_declaration",
            "struct_item", "impl_item", "type_alias_declaration", "function_item", "type_declaration"
        ):
            name_node = node.child_by_field_name("name")
            if not name_node:
                for child in node.children:
                    if child.type in ("identifier", "type_identifier", "property_identifier", "field_identifier", "name"):
                        name_node = child
                        break

            if name_node:
                symbol_name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                line_no = node.start_point[0] + 1
                first_line = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").splitlines()[0]

                kind = "function"
                if "class" in node_type or "struct" in node_type or "interface" in node_type or "type" in node_type:
                    kind = "class"
                elif "method" in node_type:
                    kind = "method"

                symbols.append({
                    "name": symbol_name,
                    "kind": kind,
                    "signature": first_line[:120].strip(),
                    "filepath": rel_path,
                    "line": line_no,
                    "docstring": ""
                })

        for child in node.children:
            self._traverse_tree_nodes(child, code_bytes, rel_path, symbols)

    def _parse_python_with_ast(self, filepath: str, rel_path: str) -> List[Dict[str, Any]]:
        """Fallback Python AST parser when Tree-sitter is unavailable."""
        symbols = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
            tree = ast.parse(code, filename=filepath)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [arg.arg for arg in node.args.args]
                    sig = f"{node.name}({', '.join(args)})"
                    docstring = ast.get_docstring(node) or ""
                    symbols.append({
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
                    symbols.append({
                        "name": node.name,
                        "kind": "class",
                        "signature": f"class {node.name}{base_str}",
                        "filepath": rel_path,
                        "line": node.lineno,
                        "docstring": docstring[:200]
                    })
        except Exception:
            pass
        return symbols

    def index_directory(self, root_dir: str = ".", force: bool = False) -> int:
        """
        Walks root_dir and incrementally indexes codebase symbols.
        Reuses cached AST symbols for files whose mtime and size haven't changed.
        Prunes removed files from the cache and updates .mesh/symbols.cache.json.
        """
        # Load cache if not already loaded and not forcing full reindex
        if not force and not self.file_cache:
            self.load_cache(root_dir)

        seen_files = set()
        indexed_files = 0
        cache_modified = False

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in LANGUAGE_EXTENSIONS:
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, root_dir).replace("\\", "/")
                    seen_files.add(rel_path)

                    try:
                        stat = os.stat(filepath)
                        mtime = stat.st_mtime
                        size = stat.st_size
                        with self._lock:
                            cached = self.file_cache.get(rel_path)

                        # Cache hit: file mtime and size match
                        if not force and cached and cached.get("mtime") == mtime and cached.get("size") == size:
                            indexed_files += 1
                            continue

                        # Cache miss or file modified: reparse AST
                        symbols = self.parse_file_symbols(filepath, root_dir=root_dir)
                        with self._lock:
                            self.file_cache[rel_path] = {
                                "mtime": mtime,
                                "size": size,
                                "symbols": symbols
                            }
                        cache_modified = True
                        indexed_files += 1
                    except Exception:
                        pass

        with self._lock:
            # Clean up deleted files from cache
            cached_paths = list(self.file_cache.keys())
            for path in cached_paths:
                if path not in seen_files:
                    del self.file_cache[path]
                    cache_modified = True

            if cache_modified or force or not self.symbol_index:
                self._rebuild_index_locked()

        self.last_indexed_at = time.time()

        if cache_modified or force:
            self.save_cache(root_dir)

        return indexed_files

    def index_file(self, filepath: str, root_dir: str = ".") -> bool:
        """
        Incrementally re-indexes a single file when edited or created.
        Updates in-memory index and persists to disk cache immediately.
        """
        if not os.path.exists(filepath):
            return self.remove_file(filepath, root_dir)

        ext = os.path.splitext(filepath)[1].lower()
        if ext not in LANGUAGE_EXTENSIONS:
            return False

        try:
            rel_path = os.path.relpath(filepath, root_dir).replace("\\", "/")
            stat = os.stat(filepath)
            symbols = self.parse_file_symbols(filepath, root_dir=root_dir)

            with self._lock:
                self.file_cache[rel_path] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "symbols": symbols
                }
                self._rebuild_index_locked()

            self.save_cache(root_dir)
            return True
        except Exception:
            return False

    def remove_file(self, filepath: str, root_dir: str = ".") -> bool:
        """Removes a deleted file from the index and cache."""
        rel_path = os.path.relpath(filepath, root_dir).replace("\\", "/")
        removed = False
        with self._lock:
            if rel_path in self.file_cache:
                del self.file_cache[rel_path]
                self._rebuild_index_locked()
                removed = True

        if removed:
            self.save_cache(root_dir)
            return True
        return False

    def start_background_indexing(
        self,
        root_dir: str = ".",
        force: bool = False,
        on_complete: Optional[Callable[[int], None]] = None
    ) -> Optional[asyncio.Task]:
        """
        Initiates asynchronous background symbol indexing without blocking the event loop.
        Immediately loads disk cache for fast readiness, then spawns a background worker
        to perform incremental directory scanning and cache updates.
        """
        # Step 1: Immediate cache load so symbols are instantly accessible
        if not force:
            self.load_cache(root_dir)

        # If already indexing, return existing task unless forced
        if self._indexing_task and not self._indexing_task.done():
            if not force:
                return self._indexing_task
            self._indexing_task.cancel()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.index_directory(root_dir, force=force)
            return None

        async def _background_worker():
            self.is_indexing = True
            try:
                count = await loop.run_in_executor(None, lambda: self.index_directory(root_dir, force=force))
                if on_complete and callable(on_complete):
                    try:
                        if asyncio.iscoroutinefunction(on_complete):
                            await on_complete(count)
                        else:
                            on_complete(count)
                    except Exception:
                        pass
                return count
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            finally:
                self.is_indexing = False

        task = loop.create_task(_background_worker())
        self._indexing_task = task
        return task

    async def wait_for_indexing(self) -> bool:
        """Awaits background indexing completion if an indexing task is currently running."""
        if self._indexing_task and not self._indexing_task.done():
            try:
                await self._indexing_task
                return True
            except Exception:
                return False
        return True

    def search_symbols(self, query: str, kind: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        """Searches indexed codebase symbols matching query and optional kind filter."""
        query_lower = query.lower().strip()
        matches = []

        with self._lock:
            current_index = list(self.symbol_index)

        for item in current_index:
            if kind and kind.lower() not in item.get("kind", "").lower():
                continue

            if (
                query_lower in item.get("name", "").lower()
                or query_lower in item.get("signature", "").lower()
                or query_lower in item.get("docstring", "").lower()
            ):
                matches.append(item)

        return matches[:limit]


# Global symbol indexer instance
symbol_indexer = SymbolIndexer()
