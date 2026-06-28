"""
src/api.py

Bonus B — FastAPI episodic memory backend.

Exposes the RAG pipeline and memory system as a REST API with the
database schema and endpoints required by the assignment.

Database schema:
  Conversations(id, created_at, title)
  Messages(id, conversation_id FK, role, content, timestamp)

Endpoints:
  GET    /conversations          — list all conversation threads
  GET    /conversation/{id}      — retrieve a specific thread's history
  POST   /message                — store a new user/AI message pair
  DELETE /conversation/{id}      — delete a thread and its messages
  GET    /health                 — server health check

Run with:
    uvicorn src.api:app --reload --port 8000

Then visit:
    http://localhost:8000/docs   ← auto-generated interactive API docs
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.retrieval import retrieve, detect_categories
from src.ingestion import build_index

# ── SETUP ──────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

client       = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-3.1-flash-lite"
TOP_K        = 5

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "memory.db")


# ── FASTAPI APP ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Gravitational Wave RAG API",
    description=(
        "REST API for the gravitational wave RAG assistant. "
        "Episodic memory backed by SQLite with Conversations and Messages tables."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── DATABASE SETUP ─────────────────────────────────────────────────────────
# Schema as required by the assignment:
#   Conversations(id, created_at, title)
#   Messages(id, conversation_id FK, role, content, timestamp)

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT    NOT NULL,
                title      TEXT    NOT NULL DEFAULT 'New Conversation'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES Conversations(id) ON DELETE CASCADE,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL
            )
        """)
        conn.commit()


@app.on_event("startup")
def startup_event():
    init_db()
    chroma_dir = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
    if not os.path.exists(chroma_dir) or not os.listdir(chroma_dir):
        print("Building ChromaDB index on startup...")
        build_index()


# ── REQUEST / RESPONSE MODELS ──────────────────────────────────────────────

class MessageRequest(BaseModel):
    # Required by the assignment: POST /message stores a user/AI pair.
    conversation_id: Optional[int] = None   # omit to start a new conversation
    user_message:    str
    title:           Optional[str] = None   # used only when creating a new conversation

class MessageResponse(BaseModel):
    conversation_id: int
    user_message_id: int
    ai_message_id:   int
    answer:          str
    categories:      list[str]
    timestamp:       str

class ConversationSummary(BaseModel):
    id:         int
    created_at: str
    title:      str
    total_messages: int

class MessageRecord(BaseModel):
    id:        int
    role:      str
    content:   str
    timestamp: str

class ConversationDetail(BaseModel):
    id:       int
    title:    str
    messages: list[MessageRecord]


# ── RAG HELPER ─────────────────────────────────────────────────────────────

RAG_PROMPT = """You are a knowledgeable assistant specialising in
gravitational wave astronomy. Answer the question using ONLY the context
provided. Be precise with numbers. If the context does not contain enough
information, say so clearly.

Context:
{context}

Question: {question}
"""

def run_rag(question: str, history: list[dict]) -> tuple[str, list[str]]:
    categories = detect_categories(question)
    chunks     = retrieve(question, top_k=TOP_K)

    if not chunks:
        return "No relevant context found.", categories

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        filename = chunk.get("metadata", {}).get("filename", "unknown")
        text     = chunk.get("text", "")
        context_parts.append(f"[{i}] Source: {filename}\n{text}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = RAG_PROMPT.format(context=context, question=question)

    # Build conversation history for multi-turn context.
    contents = []
    for msg in history:
        contents.append(
            types.Content(role=msg["role"], parts=[types.Part(text=msg["content"])])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=prompt)])
    )

    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=contents)
        return response.text.strip(), categories
    except Exception as e:
        return f"Gemini API error: {e}", categories


# ── ENDPOINTS ──────────────────────────────────────────────────────────────

# GET /conversations — list all threads
@app.get("/conversations", response_model=list[ConversationSummary])
def list_conversations():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.created_at, c.title,
                   COUNT(m.id) AS total_messages
            FROM Conversations c
            LEFT JOIN Messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]


# GET /conversation/{id} — retrieve a specific thread's history
@app.get("/conversation/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int):
    with get_db() as conn:
        conv = conn.execute(
            "SELECT id, title FROM Conversations WHERE id = ?",
            (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found.")

        msgs = conn.execute(
            "SELECT id, role, content, timestamp FROM Messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()

    return ConversationDetail(
        id=conv["id"],
        title=conv["title"],
        messages=[MessageRecord(**dict(m)) for m in msgs],
    )


# POST /message — store a new user/AI message pair
# If conversation_id is omitted, a new conversation is created automatically.
@app.post("/message", response_model=MessageResponse)
def post_message(request: MessageRequest):
    now = datetime.now().isoformat()

    with get_db() as conn:
        # Create a new conversation if none specified.
        if request.conversation_id is None:
            title = request.title or request.user_message[:50]
            cursor = conn.execute(
                "INSERT INTO Conversations (created_at, title) VALUES (?, ?)",
                (now, title)
            )
            conv_id = cursor.lastrowid
        else:
            conv_id = request.conversation_id
            existing = conn.execute(
                "SELECT id FROM Conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"Conversation {conv_id} not found.")

        # Load conversation history for multi-turn context.
        history_rows = conn.execute(
            "SELECT role, content FROM Messages WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,)
        ).fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in history_rows]

        # Run the RAG pipeline.
        answer, categories = run_rag(request.user_message, history)

        # Store the user message.
        user_cursor = conn.execute(
            "INSERT INTO Messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conv_id, "user", request.user_message, now)
        )
        user_msg_id = user_cursor.lastrowid

        # Store the AI response.
        ai_cursor = conn.execute(
            "INSERT INTO Messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conv_id, "model", answer, now)
        )
        ai_msg_id = ai_cursor.lastrowid
        conn.commit()

    return MessageResponse(
        conversation_id=conv_id,
        user_message_id=user_msg_id,
        ai_message_id=ai_msg_id,
        answer=answer,
        categories=categories,
        timestamp=now,
    )


# DELETE /conversation/{id} — delete a thread and its messages
@app.delete("/conversation/{conversation_id}")
def delete_conversation(conversation_id: int):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM Conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found.")
        conn.execute("DELETE FROM Messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM Conversations WHERE id = ?", (conversation_id,))
        conn.commit()
    return {"message": f"Conversation {conversation_id} deleted."}


# GET /health
@app.get("/health")
def health():
    return {"status": "ok", "model": GEMINI_MODEL, "timestamp": datetime.now().isoformat()}


# GET /
@app.get("/")
def root():
    return {
        "message": "Gravitational Wave RAG API",
        "docs":    "http://localhost:8000/docs",
        "version": "1.0.0",
        "endpoints": [
            "GET  /conversations",
            "GET  /conversation/{id}",
            "POST /message",
            "DELETE /conversation/{id}",
        ]
    }