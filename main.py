"""
main.py

The main entry point for the gravitational wave RAG chatbot.

Wires together all four components:
  1. ingestion.py  — builds the ChromaDB index (runs once)
  2. retrieval.py  — finds relevant chunks for each query
  3. memory.py     — short-term buffer + long-term LLM summaries
  4. Gemini API    — generates the final answer

Run with:
    python main.py
    python main.py <session_id>   # resume a past session
"""

import os
import sys

from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.retrieval import retrieve
from src.memory import ConversationMemory, save_summary, load_latest_summary
from src.ingestion import build_index


# ── CONFIGURATION ──────────────────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY not found. Add it to .env file.")
    sys.exit(1)

client       = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-3.1-flash-lite"
TOP_K        = 5


# ── SYSTEM PROMPT ──────────────────────────────────────────────────────────
# {long_term_context} is filled with the summary from the previous session.
# If this is the first ever session, it stays empty.
# {context} is the retrieved chunks for the current question.

SYSTEM_PROMPT = """You are a knowledgeable assistant specialising in
gravitational wave astronomy. You have access to a curated knowledge base
covering GW physics, LIGO/Virgo/KAGRA instrumentation, detection pipelines,
the full GWTC event catalog, and observing run history.

Answer questions using ONLY the context chunks provided below. If the context
does not contain enough information, say so clearly rather than guessing.
Be precise with numbers.

{long_term_context}

Context:
{context}

Question: {question}
"""

# Prompt used to generate the long-term summary at session end.
SUMMARY_PROMPT = """You are summarising a conversation about gravitational wave astronomy.
Write a concise summary (3-5 sentences) covering:
- The main topics discussed
- Any specific events, parameters, or facts the user asked about
- Any preferences or follow-up interests the user expressed

This summary will be shown to the assistant at the start of the next session
so it can provide continuity.

Conversation:
{history}

Summary:"""


# ── BUILD CONTEXT ──────────────────────────────────────────────────────────

def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant context found."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        meta     = chunk.get("metadata", {})
        category = meta.get("document_category", "unknown")
        filename = meta.get("filename", "unknown")
        text     = chunk.get("text", "")
        parts.append(f"[{i}] Source: {filename} (category: {category})\n{text}")
    return "\n\n---\n\n".join(parts)


# ── GENERATE ANSWER ────────────────────────────────────────────────────────

def generate_answer(
    question:         str,
    chunks:           list[dict],
    memory:           ConversationMemory,
    long_term_context: str,
) -> str:
    context = build_context(chunks)

    # Inject long-term summary only if one exists.
    lt_section = ""
    if long_term_context:
        lt_section = f"\nLong-term memory from previous sessions:\n{long_term_context}\n"

    prompt = SYSTEM_PROMPT.format(
        long_term_context=lt_section,
        context=context,
        question=question,
    )

    contents = []
    for msg in memory.get_history():
        contents.append(
            types.Content(role=msg["role"], parts=[types.Part(text=msg["parts"][0])])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=prompt)])
    )

    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=contents)
        return response.text.strip()
    except Exception as e:
        return f"[Error calling Gemini API: {e}]"


# ── GENERATE AND SAVE SUMMARY ──────────────────────────────────────────────
# Called at session end. Uses the LLM to compress the full conversation
# into a short summary that gets stored in SQLite as long-term memory.

def generate_and_save_summary(memory: ConversationMemory) -> None:
    history_text = memory.get_full_history_text()
    if not history_text.strip():
        print("[Memory] No turns to summarise.")
        return

    prompt = SUMMARY_PROMPT.format(history=history_text)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        summary = response.text.strip()
        save_summary(memory.session_id, summary)
        print(f"\n[Memory] Session summary saved:\n{summary}\n")
    except Exception as e:
        print(f"[Memory] Could not generate summary: {e}")


# ── ENSURE INDEX ───────────────────────────────────────────────────────────

def ensure_index() -> None:
    chroma_dir = os.path.join(os.path.dirname(__file__), "chroma_db")
    if not os.path.exists(chroma_dir) or not os.listdir(chroma_dir):
        print("ChromaDB index not found — building now...")
        build_index()
    else:
        print("ChromaDB index found.\n")


# ── CHAT LOOP ──────────────────────────────────────────────────────────────

def chat_loop(memory: ConversationMemory, long_term_context: str) -> None:
    print("=" * 60)
    print("  Gravitational Wave RAG Assistant")
    print("  Model:", GEMINI_MODEL)
    print("  Session:", memory.session_id)
    if long_term_context:
        print("  Long-term memory: loaded from previous session")
    print("=" * 60)
    print("Commands: 'quit' to exit | 'status' | 'clear'\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGenerating session summary...")
            generate_and_save_summary(memory)
            print("Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Generating session summary...")
            generate_and_save_summary(memory)
            print("Goodbye!")
            break

        if user_input.lower() == "status":
            print(f"[Memory] {memory.status()}")
            continue

        if user_input.lower() == "clear":
            memory.clear_buffer()
            continue

        print("Retrieving...", end=" ", flush=True)
        chunks = retrieve(user_input, top_k=TOP_K)
        print(f"got {len(chunks)} chunks.")
        print("Thinking...\n")

        answer = generate_answer(user_input, chunks, memory, long_term_context)
        memory.add_turn(user_input, answer)
        print(f"Assistant: {answer}\n")


# ── ENTRY POINT ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_index()

    session_id = sys.argv[1] if len(sys.argv) > 1 else None
    memory     = ConversationMemory(session_id=session_id)

    # Load the most recent session summary for long-term context.
    # This is empty on the very first run.
    long_term_context = load_latest_summary()
    if long_term_context:
        print(f"[Memory] Long-term context loaded from previous session.\n")

    chat_loop(memory, long_term_context)