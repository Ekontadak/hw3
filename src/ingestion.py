"""
src/ingestion.py

Reads every file in data/, converts it to plain text chunks,
attaches metadata to each chunk, and loads everything into a
local ChromaDB vector database that lives in chroma_db/.

Run once to build the index, then leave it alone:
    python -m src.ingestion

Re-run only if you change or add files in data/.
"""

import os
import json
import hashlib

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


# ── 1. PATHS ──────────────────────────────────────────────────────────────
# All paths are relative to this file so the project works from any directory.

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")

COLLECTION_NAME = "gw_knowledge_base"


# ── 2. CHUNKING SETTINGS ──────────────────────────────────────────────────
# CHUNK_SIZE:    how many characters go into each chunk.
# CHUNK_OVERLAP: how many characters are shared between one chunk and the next.
# Overlap stops a sentence that straddles a boundary from being lost.

CHUNK_SIZE    = 800
CHUNK_OVERLAP = 150


# ── 3. PER-FILE METADATA ──────────────────────────────────────────────────
# Every chunk inherits the metadata of the file it came from.
# document_category is the key field: retrieval.py uses it to pre-filter
# ChromaDB to only the files that are relevant to a given query type.

FILE_META = {
    "gw150914_detection.pdf": {
        "document_category": "detection_research",
        "source": "Abbott et al. (2016) Phys. Rev. Lett. 116, 061102. arXiv:1602.03837",
        "author": "B.P. Abbott et al. (LIGO Scientific Collaboration and Virgo Collaboration)",
    },
    "gw_detection_pipelines.md": {
        "document_category": "analysis_software",
        "source": "Usman et al. 2016, Messick et al. 2017, Sachdev et al. 2019, "
                  "Aubin et al. 2021, Veitch et al. 2015, Ashton et al. 2019",
        "author": "Compiled by student; each claim verified against cited papers",
    },
    "gwtc_catalog.json": {
        "document_category": "event_catalog",
        "source": "GWOSC Public API v2: gwosc.org/api/v2/event-versions",
        "author": "LIGO-Virgo-KAGRA Collaboration / Gravitational Wave Open Science Center",
    },
    "observing_runs.json": {
        "document_category": "observing_runs",
        "source": "Compiled from gwosc.org/data/, gwosc.org/O4/O4a, gwosc.org/O4/O4b",
        "author": "Self Created, dates and GPS times verified against GWOSC pages",
    },
    "gw_events.xlsx": {
        "document_category": "event_parameters",
        "source": "GWOSC Event API: gwosc.org/eventapi/",
        "author": "LIGO-Virgo-KAGRA Collaboration / Gravitational Wave Open Science Center",
    },
    "ligo_learn_more.html": {
        "document_category": "educational_explainer",
        "source": "LIGO Laboratory Caltech: ligo.caltech.edu/page/learn-more",
        "author": "LIGO Laboratory, Caltech and MIT. NSF Award PHY-2309200",
    },
    "GW_wikipedia.html": {
        "document_category": "educational_explainer",
        "source": "Wikipedia: en.wikipedia.org/wiki/Gravitational_wave",
        "author": "Wikipedia contributors. Licensed under CC BY-SA 4.0",
    },
}


# ── 4. TEXT CHUNKER ───────────────────────────────────────────────────────
# Splits a long string into overlapping windows of fixed character length.
# Returns a list of strings, each one ready to be embedded.

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    text   = text.strip()
    start  = 0

    while start < len(text):
        end   = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap   # slide forward, keeping the overlap

    return chunks


# ── 5. FILE PARSERS ───────────────────────────────────────────────────────
# Each parser returns a list of (text, extra_metadata) tuples.
# For plain text files the list is just one tuple — the full text plus an
# empty metadata dict, and chunk_text handles splitting later.
# For structured files (JSON, XLSX) each record becomes its own tuple so
# individual events stay together and never straddle a chunk boundary.


def parse_pdf(filepath: str) -> list[tuple[str, dict]]:
    # pdfplumber reads each page and extracts the text layer.
    # Pages are joined with double newlines to preserve structure.
    pages = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text.strip())
    full_text = "\n\n".join(pages)
    return [(full_text, {})]


def parse_markdown(filepath: str) -> list[tuple[str, dict]]:
    # Markdown is plain text — just read and return the whole file.
    with open(filepath, "r", encoding="utf-8") as f:
        return [(f.read(), {})]


def parse_html(filepath: str) -> list[tuple[str, dict]]:
    # BeautifulSoup parses the HTML. Navigation, scripts, and styles are
    # removed first so chunks don't contain sidebar menus or JS code.
    # This is especially important for potential addition files which are full
    # browser saves with lots of navigation links and sidebars.
    with open(filepath, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "noscript", "link", "meta"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Collapse runs of blank lines left behind after tag removal.
    lines    = text.splitlines()
    cleaned  = []
    prev_blank = False
    for line in lines:
        if line.strip() == "":
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False

    return [("\n".join(cleaned), {})]


def parse_json_catalog(filepath: str) -> list[tuple[str, dict]]:
    # gwtc_catalog.json holds 433 event records.
    # Each event becomes its own chunk so queries like "which detectors
    # observed GW170817" can retrieve the right record directly.
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for event in data.get("results", []):
        detectors = ", ".join(event.get("detectors", [])) or "unknown"
        text = (
            f"Event: {event['name']} | "
            f"Catalog: {event.get('catalog', 'unknown')} | "
            f"GPS: {event.get('gps', 'unknown')} | "
            f"Detectors: {detectors} | "
            f"Version: {event.get('version', 'unknown')} | "
            f"DOI: {event.get('doi', 'none')}"
        )
        # Store the event name in metadata so filters can target a specific event.
        records.append((text, {"event_name": event["name"]}))

    return records


def parse_json_runs(filepath: str) -> list[tuple[str, dict]]:
    # observing_runs.json holds 6 run summaries (O1–O4b).
    # Each run becomes its own chunk.
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for run in data.get("observing_runs", []):
        notable = ", ".join(run.get("notable_events", [])) or "none listed"
        detectors = ", ".join(run.get("detectors_online", [])) or "unknown"
        text = (
            f"Run: {run['run']} ({run.get('full_name', '')}) | "
            f"Start: {run.get('start_date', '?')} | "
            f"End: {run.get('end_date', '?')} | "
            f"Duration: {run.get('duration_days', '?')} days | "
            f"GPS: {run.get('gps_start', '?')} – {run.get('gps_end', '?')} | "
            f"Detectors: {detectors} | "
            f"Notable events: {notable} | "
            f"Notes: {run.get('notes', '')}"
        )
        records.append((text, {"run": run["run"]}))

    return records


def parse_xlsx(filepath: str) -> list[tuple[str, dict]]:
    df = pd.read_excel(filepath)

    # Columns that duplicate the JSON catalog — skip them.
    SKIP_COLS = {'shortName', 'gps', 'version', 'catalog', 'doi', 'detail_url'}

    records = []
    for _, row in df.iterrows():
        event_name = str(row.get('name', 'unknown'))
        parts = [f"Event: {event_name}"]  # always first

        for col, val in row.items():
            if col == 'name':
                continue
            if col in SKIP_COLS:
                continue
            if pd.notna(val) and str(val).strip():
                parts.append(f"{col}: {val}")

        text  = " | ".join(parts)
        extra = {"event_name": event_name}
        records.append((text, extra))

    return records


# ── 6. ROUTER ─────────────────────────────────────────────────────────────
# Looks at the filename and calls the right parser.
# Returns a flat list of (text_chunk, metadata_dict) tuples ready for ChromaDB.

def route_and_parse(filepath: str) -> list[tuple[str, dict]]:
    filename = os.path.basename(filepath)
    base_meta = FILE_META.get(filename, {})

    # ── dispatch by filename / extension ──
    if filename.endswith(".pdf"):
        raw = parse_pdf(filepath)

    elif filename.endswith(".md"):
        raw = parse_markdown(filepath)

    elif filename.endswith(".html"):
        raw = parse_html(filepath)

    elif filename == "gwtc_catalog.json":
        # catalog: pre-chunked — one record per event, no further splitting
        raw = parse_json_catalog(filepath)
        return [
            (text, {**base_meta, **extra})
            for text, extra in raw
            if text.strip()
        ]

    elif filename == "observing_runs.json":
        # runs: pre-chunked — one record per run
        raw = parse_json_runs(filepath)
        return [
            (text, {**base_meta, **extra})
            for text, extra in raw
            if text.strip()
        ]

    elif filename.endswith(".xlsx"):
        # XLSX: pre-chunked — one record per row
        raw = parse_xlsx(filepath)
        return [
            (text, {**base_meta, **extra})
            for text, extra in raw
            if text.strip()
        ]

    else:
        print(f"  [WARN] No parser for {filename}, skipping.")
        return []

    # ── for text-based files: apply sliding-window chunking ──
    # raw is a list of (full_text, {}) from the parsers above.
    # We split the full text into overlapping chunks here.
    results = []
    for full_text, extra in raw:
        for chunk in chunk_text(full_text):
            results.append((chunk, {**base_meta, **extra}))

    return results


# ── 7. UNIQUE CHUNK ID ────────────────────────────────────────────────────
# ChromaDB requires a unique string ID for every document it stores.
# We hash the text content so duplicate chunks never get inserted twice.

def make_chunk_id(filename: str, index: int, text: str) -> str:
    digest = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{filename}__chunk{index:04d}__{digest}"


# ── 8. BUILD INDEX ────────────────────────────────────────────────────────
# Connects to (or creates) the ChromaDB collection, iterates over all files
# in data/, parses and chunks them, then upserts everything into the DB.
# "Upsert" means it inserts new chunks and skips ones that already exist,
# so re-running this function is safe and won't create duplicates.

def build_index(force_rebuild: bool = False) -> chromadb.Collection:
    # Use sentence-transformers to turn text chunks into embedding vectors.
    # all-MiniLM-L6-v2 is fast, small (80MB), and works well for retrieval.
    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # PersistentClient saves the database to disk at CHROMA_DIR so we
    # don't have to re-embed everything every time the program starts.
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # If force_rebuild is True, wipe the old collection and start fresh.
    if force_rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"Deleted existing collection '{COLLECTION_NAME}'.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},   # cosine similarity for embeddings
    )

    # ── iterate over every known file ──
    total_chunks = 0
    for filename in FILE_META:
        filepath = os.path.join(DATA_DIR, filename)

        if not os.path.exists(filepath):
            print(f"  [SKIP] {filename} not found in data/")
            continue

        print(f"  Parsing {filename}...")
        chunks = route_and_parse(filepath)

        if not chunks:
            print(f"  [WARN] No chunks produced from {filename}")
            continue

        # ── upsert in batches of 100 ──
        # ChromaDB handles large upserts fine, but batching keeps memory low
        # when dealing with files like the 433-row XLSX.
        BATCH = 100
        for batch_start in range(0, len(chunks), BATCH):
            batch = chunks[batch_start : batch_start + BATCH]

            ids        = []
            texts      = []
            metadatas  = []

            for i, (text, meta) in enumerate(batch):
                chunk_index = batch_start + i
                ids.append(make_chunk_id(filename, chunk_index, text))
                texts.append(text)
                # Attach the filename itself so we can trace any chunk back to its file.
                metadatas.append({**meta, "filename": filename})

            collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
            )

        total_chunks += len(chunks)
        print(f"  Done — {len(chunks)} chunks from {filename}")

    print(f"\nIndex built: {total_chunks} total chunks in '{COLLECTION_NAME}'.")
    return collection


# ── 9. ENTRY POINT ────────────────────────────────────────────────────────
# Run this file directly to build (or rebuild) the index.
# Pass --rebuild as a command-line argument to force a fresh start.

if __name__ == "__main__":
    import sys
    force = "--rebuild" in sys.argv
    print(f"Building ChromaDB index (force_rebuild={force})...")
    build_index(force_rebuild=force)