import os
import re
from typing import Dict, Any, List, Optional, Set, Tuple
import symbol_search
from theme import console


class RepoMapGenerator:
    """
    Generates a token-compact Markdown repository map by extracting symbols
    from symbol_search.symbol_indexer, building an import/reference dependency graph,
    and ranking top architectural symbols using PageRank centrality.
    """
    def __init__(self):
        pass

    def build_dependency_graph(self) -> Tuple[Dict[str, Set[str]], Dict[str, int]]:
        """
        Builds a call/import dependency graph from symbol_search.symbol_indexer.
        Returns (graph_edges, symbol_frequencies).
        """
        symbols = symbol_search.symbol_indexer.symbol_index
        if not symbols:
            symbol_search.symbol_indexer.index_directory(".")
            symbols = symbol_search.symbol_indexer.symbol_index

        graph_edges: Dict[str, Set[str]] = {}
        symbol_freqs: Dict[str, int] = {}

        # Collect all known symbol names
        known_symbols = {s["name"] for s in symbols if s.get("name")}

        for sym in symbols:
            filepath = sym.get("filepath", "")
            name = sym.get("name", "")
            if not filepath or not name:
                continue

            graph_edges.setdefault(filepath, set())
            symbol_freqs.setdefault(name, 0)

            # Check if symbol name is referenced in signatures or docstrings of other files
            for other_sym in symbols:
                other_file = other_sym.get("filepath", "")
                if other_file != filepath:
                    if name.lower() in other_sym.get("signature", "").lower() or name.lower() in other_sym.get("docstring", "").lower():
                        graph_edges[filepath].add(other_file)
                        symbol_freqs[name] += 1

        return graph_edges, symbol_freqs

    def compute_pagerank(
        self,
        graph: Dict[str, Set[str]],
        damping: float = 0.85,
        iterations: int = 15
    ) -> Dict[str, float]:
        """Computes PageRank centrality scores for files in the dependency graph."""
        nodes = list(graph.keys())
        if not nodes:
            return {}

        num_nodes = len(nodes)
        initial_score = 1.0 / num_nodes
        scores = {node: initial_score for node in nodes}

        for _ in range(iterations):
            new_scores = {}
            for node in nodes:
                incoming_score = 0.0
                for other_node, neighbors in graph.items():
                    if node in neighbors and len(neighbors) > 0:
                        incoming_score += scores[other_node] / len(neighbors)
                new_scores[node] = (1.0 - damping) / num_nodes + damping * incoming_score
            scores = new_scores

        return scores

    def generate_repo_map(self, root_dir: str = ".", token_budget: int = 500) -> str:
        """
        Generates a token-compact Markdown tree map of the repository's key symbols
        ranked by architectural importance.
        """
        symbols = symbol_search.symbol_indexer.symbol_index
        if not symbols:
            symbol_search.symbol_indexer.index_directory(root_dir)
            symbols = symbol_search.symbol_indexer.symbol_index

        if not symbols:
            return ""

        graph, freqs = self.build_dependency_graph()
        pagerank = self.compute_pagerank(graph)

        # Sort files by PageRank score descending
        sorted_files = sorted(
            pagerank.keys(),
            key=lambda f: (pagerank.get(f, 0.0), len([s for s in symbols if s.get("filepath") == f])),
            reverse=True
        )

        if not sorted_files:
            file_symbol_counts = {}
            for s in symbols:
                fp = s.get("filepath", "")
                if fp:
                    file_symbol_counts[fp] = file_symbol_counts.get(fp, 0) + 1
            sorted_files = sorted(file_symbol_counts.keys(), key=lambda f: file_symbol_counts[f], reverse=True)

        lines = ["## Repository Architecture Map (Key Symbols)"]
        char_count = len(lines[0])
        max_chars = token_budget * 4  # ~4 chars per token heuristic

        for filepath in sorted_files:
            file_symbols = [s for s in symbols if s.get("filepath") == filepath]
            if not file_symbols:
                continue

            file_header = f"\n`{filepath}`:"
            if char_count + len(file_header) > max_chars:
                lines.append("  [... truncated for token budget ...]")
                break

            lines.append(file_header)
            char_count += len(file_header)

            # Sort symbols in file by frequency
            file_symbols.sort(key=lambda s: (freqs.get(s["name"], 0), -s.get("line", 0)), reverse=True)

            for sym in file_symbols[:6]:  # max 6 key symbols per file
                sig = sym.get("signature", sym.get("name", ""))
                sym_line = f"  - {sig}"
                if char_count + len(sym_line) > max_chars:
                    break
                lines.append(sym_line)
                char_count += len(sym_line)

        return "\n".join(lines)


# Global repo map generator instance
repo_map_generator = RepoMapGenerator()


def get_repo_map_instructions(root_dir: str = ".", token_budget: int = 500) -> str:
    """Returns Markdown repo map section for system prompt injection."""
    return repo_map_generator.generate_repo_map(root_dir, token_budget=token_budget)