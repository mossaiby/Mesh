"""
A small, dependency-free local "embedding" search: TF-IDF-weighted sparse
vectors over word unigrams/bigrams and character trigrams, compared with
cosine similarity.

This exists as the fast, free, offline alternative to `memory_search.py`'s
LLM-based approach (which sends the *entire* memory store as a prompt on
every query). That approach genuinely understands paraphrases and synonyms
in a way nothing here can, but it costs a real model call and a real chunk
of context window every time, and it stops scaling the moment a memory
store gets too big to fit in a single prompt. This module never leaves the
process, costs no tokens, and comfortably handles far more entries - at
the cost of being lexical rather than truly semantic: it catches shared
words, word order variants, and partial/typo'd terms (via the character
trigrams), but it won't connect "CI provider" to "continuous integration
tool" the way an LLM would.

Both engines are kept and exposed side by side (see `memory_search.py` and
`tools/memory_tool.py`) rather than one replacing the other, since which
one is worth its cost depends on the query and the store size - a
judgment call left to whichever model is calling the `memory` tool.
"""

import math
import re
from collections import Counter
from typing import Dict, Any, List, Tuple

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> Tuple[List[str], List[str]]:
    """Returns (word_features, char_features) for one piece of text.

    Kept as two separate feature groups rather than one combined bag: word
    unigrams/bigrams are the real signal, while character trigrams are only
    meant to refine ranking between candidates that already share real words
    (catching morphological variants like "config" vs "configure"). If
    trigrams were mixed into the same similarity score unconditionally, a
    short memory entry and a totally unrelated query can end up sharing one
    coincidental trigram (e.g. "wildly" / "Fly.io" both contain "ly ") and,
    with very few documents in the store, that alone can be enough to clear
    a naive threshold. See `_score()` below for how the two are combined.
    """
    words = _WORD_RE.findall(text.lower())
    word_features = list(words)
    word_features.extend(f"{a}_{b}" for a, b in zip(words, words[1:]))

    joined = " ".join(words)
    char_features = [f"#{joined[i:i + 3]}" for i in range(len(joined) - 2)] if len(joined) >= 3 else []

    return word_features, char_features


def _term_freqs(features: List[str]) -> Counter:
    return Counter(features)


def _build_vectors(feature_lists: Dict[str, List[str]]) -> Tuple[Dict[str, Counter], Dict[str, float]]:
    """Computes TF vectors for each document plus IDF weights derived from
    the document set itself (there's no persistent corpus to draw IDF from -
    the memory store *is* the corpus, recomputed fresh each search, which is
    cheap at the sizes this is meant for)."""
    tf_vectors = {doc_id: _term_freqs(features) for doc_id, features in feature_lists.items()}

    doc_freq: Counter = Counter()
    for tf in tf_vectors.values():
        doc_freq.update(tf.keys())

    n_docs = max(len(tf_vectors), 1)
    idf = {term: math.log((n_docs + 1) / (df + 1)) + 1.0 for term, df in doc_freq.items()}
    return tf_vectors, idf


def _weighted(tf: Counter, idf: Dict[str, float]) -> Dict[str, float]:
    return {term: count * idf.get(term, 0.0) for term, count in tf.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    shared = a.keys() & b.keys()
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# Below this cosine similarity, a match is considered too weak to surface -
# tuned loosely rather than precisely, since this is meant to be a cheap
# first pass, not the final word (see `SafetyGuard`-style layering: this is
# the fast static layer, the LLM search is the fallback with real judgment).
DEFAULT_MIN_SCORE = 0.12


def embedding_search(query: str, memory: Dict[str, Any], top_k: int = 5,
                      min_score: float = DEFAULT_MIN_SCORE) -> List[Dict[str, Any]]:
    """Ranks memory entries against `query` by local lexical similarity.
    Returns a list of {"key", "value", "score"} dicts, most relevant first,
    for entries scoring at least `min_score`. Pure computation, no I/O,
    no network, no model call."""
    if not memory or not query or not query.strip():
        return []

    documents = {key: f"{key} {value}" for key, value in memory.items()}
    doc_word_features = {}
    doc_char_features = {}
    for key, text in documents.items():
        words, chars = _tokens(text)
        doc_word_features[key] = words
        doc_char_features[key] = chars

    word_tf, word_idf = _build_vectors(doc_word_features)
    char_tf, char_idf = _build_vectors(doc_char_features)
    word_vectors = {doc_id: _weighted(tf, word_idf) for doc_id, tf in word_tf.items()}
    char_vectors = {doc_id: _weighted(tf, char_idf) for doc_id, tf in char_tf.items()}

    query_words, query_chars = _tokens(query)
    query_word_vector = _weighted(_term_freqs(query_words), word_idf)
    query_char_vector = _weighted(_term_freqs(query_chars), char_idf)

    scored = []
    for key in documents:
        word_sim = _cosine(query_word_vector, word_vectors[key])
        # Character-trigram similarity only counts once there is at least
        # some real word-level overlap - otherwise a single coincidental
        # shared trigram between two otherwise-unrelated short strings can
        # manufacture a match out of nothing (see the docstring on
        # `_tokens()`).
        char_sim = _cosine(query_char_vector, char_vectors[key]) if word_sim > 0 else 0.0
        score = (0.85 * word_sim) + (0.15 * char_sim)
        scored.append((key, score))

    scored = [(key, score) for key, score in scored if score >= min_score]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    return [
        {"key": key, "value": memory[key], "score": round(score, 4)}
        for key, score in scored[:top_k]
    ]
