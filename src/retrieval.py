"""
src/retrieval.py

Takes a user query, figures out which document categories are relevant,
searches ChromaDB using dense vector similarity, re-ranks the results
using BM25 (keyword matching), then combines both rankings with
Reciprocal Rank Fusion (RRF) to produce a final ordered list of chunks.

The retriever is what sits between the user's question and the LLM.
Its job is to pull the right chunks out of the 2000+ stored in ChromaDB
so the LLM only sees relevant context, not everything.
"""

import os
import re
import math
from collections import defaultdict

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


# ── 1. CONNECTION ─────────────────────────────────────────────────────────
# Points at the same ChromaDB folder that ingestion.py wrote to.
# The embedding function must be identical to the one used at index time —
# if they differ, the vectors won't be comparable.

CHROMA_DIR      = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "gw_knowledge_base"

_client     = None
_collection = None

def get_collection() -> chromadb.Collection:
    # Opens the database connection once and reuses it for every query.
    # Re-opening on every call would be slow and wasteful.
    global _client, _collection
    if _collection is None:
        embed_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn,
        )
    return _collection


# ── 2. CATEGORY ROUTER ────────────────────────────────────────────────────
# Reads the query and decides which document_category values to search.
# This runs before the vector search so ChromaDB only compares the query
# against a relevant subset of chunks instead of all 2000+.
#
# The logic is keyword-based — fast, transparent, and easy to extend.
# A more advanced version could use an LLM classifier here.

# Maps each category to the keywords that suggest a query belongs there.
CATEGORY_KEYWORDS = {
    "event_parameters": [
        "mass", "chirp", "distance", "redshift", "snr", "far", "p_astro",
        "spin", "chi_eff", "luminosity", "solar mass", "mpc", "megaparsec",
        "parameter", "measurement", "value", "how heavy", "how far",
        "final mass", "total mass",
    ],
    "event_catalog": [
        "catalog", "gwtc", "detector", "observed by", "which detector",
        "h1", "l1", "v1", "hanford", "livingston", "virgo", "kagra",
        "gps", "timestamp", "doi", "version", "shortname",
    ],
    "observing_runs": [
    "observing run", "o1", "o2", "o3", "o4", "o3a", "o3b", "o4a", "o4b",
    "when did", "start", "end", "duration", "how long", "operational",
    "online", "offline", "commissioning", "run", "detectors online",
    "which detectors were", "were online", "during o4", "during o3",
    "during o2", "during o1",
],
    "analysis_software": [
        "pipeline", "pycbc", "gstlal", "mbta", "matched filter", "snr",
        "template", "bank", "chi squared", "coincidence", "alert",
        "early warning", "bilby", "lalinference", "parameter estimation",
        "bayesian", "sampler", "dynesty", "false alarm", "far",
        "detection statistic", "ranking", "veto", "data quality",
    ],
    "detection_research": [
        "gw150914", "first detection", "first observation", "september 2015",
        "binary black hole", "merger", "1.3 billion", "29 solar", "36 solar",
        "62 solar", "general relativity", "gr test", "waveform",
        "significance", "sigma", "confidence",
    ],
    "educational_explainer": [
        "what is", "how does", "explain", "why", "history", "einstein",
        "interferometer", "arm", "laser", "mirror", "seismic", "vacuum",
        "polarization", "strain", "spacetime", "ripple", "wave",
        "neutron star", "black hole", "pulsar", "continuous", "stochastic",
        "burst", "inspiral", "quadrupole", "weber bar", "lisa", "kagra",
        "einstein telescope", "multi-messenger",
    ],
}

def detect_categories(query: str) -> list[str]:
    # Lowercases the query and counts how many keywords from each category
    # appear in it. Returns all categories that got at least one hit.
    # If nothing matches, returns all categories so no results are missed.
    query_lower = query.lower()
    scores      = defaultdict(int)

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                scores[category] += 1

    matched = [cat for cat, score in scores.items() if score > 0]

    # Some queries mention a specific event name like "GW170817" — always
    # include event_parameters and event_catalog for those.
    if re.search(r"gw\d{6}", query_lower):
        for cat in ("event_parameters", "event_catalog"):
            if cat not in matched:
                matched.append(cat)
    # If a specific run name is mentioned, force observing_runs only —
    # remove event_catalog so it doesn't dominate the results.
    run_names = ["o1", "o2", "o3a", "o3b", "o4a", "o4b", "o3", "o4"]
    if any(f" {rn} " in f" {query_lower} " or query_lower.endswith(f" {rn}")
           or query_lower.endswith(f" {rn}?")
           for rn in run_names):
        matched = [c for c in matched if c != "event_catalog"]
        if "observing_runs" not in matched:
            matched.append("observing_runs")

    # Fall back to searching everything if no keywords matched at all.
    return matched if matched else list(CATEGORY_KEYWORDS.keys())


# ── 3. DENSE RETRIEVAL ────────────────────────────────────────────────────
# Embeds the query with the same model used at index time, then asks
# ChromaDB to return the N most similar chunks using cosine similarity.
# The `where` clause applies the category filter before the search runs.

def dense_search(
    query: str,
    categories: list[str],
    n_results: int = 20,
) -> list[dict]:
    collection = get_collection()

    # If query mentions a specific event name like GW150914 or GW170817,
    # filter to that event directly so we don't get random other events.
    event_match = re.search(r"gw\d{6}", query.lower())
    if event_match:
        event_name = event_match.group().upper()
        where = {
            "$and": [
                {"document_category": {"$in": categories}},
                {"event_name": {"$eq": event_name}}
            ]
        }
    else:
        where = {"document_category": {"$in": categories}}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        # If the event_name filter returns no results, fall back to
        # category-only filter so the query never returns empty.
        where = {"document_category": {"$in": categories}}
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    # Unpack ChromaDB's nested response into a flat list of dicts.
    hits = []
    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(docs, metadatas, distances):
        hits.append({
            "text":     doc,
            "metadata": meta,
            "score":    1 - dist,
        })

    return hits

# ── 4. BM25 ───────────────────────────────────────────────────────────────
# BM25 is a classical keyword-matching algorithm (the same family as
# TF-IDF but with length normalisation). It scores documents by how
# often query terms appear in them, penalising very long documents.

# We run BM25 only over the candidates already returned by dense search —
# not over the full 2000+ chunk index — so it stays fast.

class BM25:
    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        # k1 controls term frequency saturation (higher = more weight on freq)
        # b controls document length normalisation (1.0 = full normalisation)
        self.k1     = k1
        self.b      = b
        self.corpus = corpus

        # Tokenise: split on whitespace and non-alphanumeric characters,
        # lowercase everything.
        self.tokenised = [self._tokenise(doc) for doc in corpus]

        # Document frequency: how many documents contain each term.
        self.df = defaultdict(int)
        for tokens in self.tokenised:
            for term in set(tokens):
                self.df[term] += 1

        self.N      = len(corpus)
        self.avgdl  = sum(len(t) for t in self.tokenised) / max(self.N, 1)

    def _tokenise(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def score(self, query: str) -> list[float]:
        # Returns a BM25 score for every document in the corpus.
        query_terms = self._tokenise(query)
        scores      = []

        for tokens in self.tokenised:
            tf_map = defaultdict(int)
            for t in tokens:
                tf_map[t] += 1

            doc_score = 0.0
            dl = len(tokens)

            for term in query_terms:
                if term not in tf_map:
                    continue
                # IDF — terms that appear in many documents get lower weight.
                idf = math.log((self.N - self.df[term] + 0.5) /
                               (self.df[term] + 0.5) + 1)
                # TF with saturation and length normalisation.
                tf  = tf_map[term]
                tf_norm = (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
                doc_score += idf * tf_norm

            scores.append(doc_score)

        return scores


# ── 5. RECIPROCAL RANK FUSION ─────────────────────────────────────────────
# RRF combines two ranked lists into one without needing to normalize their
# scores onto the same scale .
# The document that ranks highly in BOTH lists ends up at the top.

def reciprocal_rank_fusion(
    dense_hits: list[dict],
    bm25_scores: list[float],
    k: int = 60,
) -> list[dict]:
    # Dense hits are already in rank order (best first).
    # BM25 scores are raw floats — we sort them to get ranks.

    n = len(dense_hits)

    # RRF score from the dense ranking (position 0 = rank 1).
    rrf_dense = {i: 1.0 / (k + rank + 1) for rank, i in enumerate(range(n))}

    # RRF score from BM25 ranking — sort indices by descending BM25 score.
    bm25_order = sorted(range(n), key=lambda i: bm25_scores[i], reverse=True)
    rrf_bm25   = {idx: 1.0 / (k + rank + 1)
                  for rank, idx in enumerate(bm25_order)}

    # Combine: add both RRF scores for each document.
    combined = []
    for i, hit in enumerate(dense_hits):
        rrf_score = rrf_dense.get(i, 0) + rrf_bm25.get(i, 0)
        combined.append({**hit, "rrf_score": rrf_score})

    # Sort by combined RRF score, highest first.
    combined.sort(key=lambda x: x["rrf_score"], reverse=True)
    return combined


# ── 6. MAIN RETRIEVE FUNCTION ─────────────────────────────────────────────
# This is the only function that main.py and evaluate.py need to call.

def retrieve(
    query:      str,
    top_k:      int  = 5,
    n_dense:    int  = 20,
) -> list[dict]:
    """
    Returns the top_k most relevant chunks for the given query.

    Each returned item is a dict with:
        text       — the chunk text to pass to the LLM
        metadata   — document_category, source, author, filename, etc.
        rrf_score  — combined relevance score (higher = better)
    """

    # Step 1 — figure out which categories to search.
    categories = detect_categories(query)

    # Step 2 — dense vector search over the relevant categories.
    dense_hits = dense_search(query, categories, n_results=n_dense)

    if not dense_hits:
        return []

    # Step 3 — score the same candidates with BM25.
    corpus      = [h["text"] for h in dense_hits]
    bm25        = BM25(corpus)
    bm25_scores = bm25.score(query)

    # Step 4 — fuse the two rankings with RRF.
    fused = reciprocal_rank_fusion(dense_hits, bm25_scores)

    # Step 5 — return just the top_k results.
    return fused[:top_k]


# ── 7. QUICK TEST ─────────────────────────────────────────────────────────
# Run this file directly to test the retriever against a few sample queries.
# Requires the ChromaDB index to have been built first by ingestion.py.

if __name__ == "__main__":
    test_queries = [
        "What is the chirp mass of GW150914?",
        "How does PyCBC detect gravitational waves?",
        "Which detectors observed GW170817?",
        "When did observing run O3b end?",
        "What are the four types of gravitational waves?",
    ]

    for q in test_queries:
        print(f"\nQuery: {q}")
        cats = detect_categories(q)
        print(f"  Categories: {cats}")
        results = retrieve(q, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"  [{i}] ({r['metadata'].get('document_category')}) "
                  f"score={r['rrf_score']:.4f} | "
                  f"{r['text'][:120]}...")