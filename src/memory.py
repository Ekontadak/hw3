"""
src/memory.py

Manages conversation history at two levels:

  Short-term — a list of the last N turns kept in RAM.
               Passed to Gemini on every call so it knows what was
               said earlier in the current conversation.

  Long-term  — an LLM-generated summary of each session, saved to
               SQLite. Loaded at the start of the next session and
               injected into the system prompt so the assistant
               remembers context across restarts.

"""

import os
import sqlite3
import uuid
from datetime import datetime


# ── SETTINGS ───────────────────────────────────────────────────────────────
# SHORT_TERM_TURNS: how many recent turns to keep in the active buffer.
# 6 turns = 6 user messages + 6 assistant replies = 12 messages total.

SHORT_TERM_TURNS = 6

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "memory.db")


# ── DATABASE SETUP ─────────────────────────────────────────────────────────
# Two tables:
#   conversations — raw turn-by-turn history (short-term source, volatile)
#   summaries     — LLM-generated session summaries (long-term, persistent)

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_connection() as conn:
        # Raw message history — used to rehydrate the short-term buffer.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL
            )
        """)
        # LLM-generated summaries — the actual long-term memory.
        # One row per session, written at session end.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                summary     TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL
            )
        """)
        conn.commit()

_init_db()


# ── MEMORY CLASS ───────────────────────────────────────────────────────────

class ConversationMemory:

    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._buffer: list[dict] = []

        if session_id:
            self._load_from_db()

        print(f"[Memory] Session '{self.session_id}' started. "
              f"Buffer has {len(self._buffer) // 2} prior turns.")

    # ── ADD A TURN ─────────────────────────────────────────────────────────
    # Saves the raw exchange to SQLite and keeps the short-term buffer trimmed.

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (self.session_id, "user", user_message, now)
            )
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (self.session_id, "model", assistant_message, now)
            )
            conn.commit()

        self._buffer.append({"role": "user",  "parts": [user_message]})
        self._buffer.append({"role": "model", "parts": [assistant_message]})

        # Keep only the last SHORT_TERM_TURNS turns in RAM.
        max_messages = SHORT_TERM_TURNS * 2
        if len(self._buffer) > max_messages:
            self._buffer = self._buffer[-max_messages:]

    # ── GET HISTORY ────────────────────────────────────────────────────────
    # Returns the short-term buffer in the format Gemini expects.

    def get_history(self) -> list[dict]:
        return list(self._buffer)

    # ── CLEAR BUFFER ───────────────────────────────────────────────────────

    def clear_buffer(self) -> None:
        self._buffer = []
        print("[Memory] Short-term buffer cleared.")

    # ── LOAD FROM DB ───────────────────────────────────────────────────────
    # Rehydrates the short-term buffer from the raw message log.
    # Called when resuming an existing session.

    def _load_from_db(self) -> None:
        with _get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (self.session_id, SHORT_TERM_TURNS * 2)
            ).fetchall()

        for row in reversed(rows):
            self._buffer.append({
                "role":  row["role"],
                "parts": [row["content"]],
            })

    # ── GET RAW HISTORY FOR SUMMARISATION ──────────────────────────────────
    # Returns the full conversation as a plain text string.
    # Passed to the LLM when generating the long-term summary at session end.

    def get_full_history_text(self) -> str:
        with _get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations "
                "WHERE session_id = ? ORDER BY id ASC",
                (self.session_id,)
            ).fetchall()

        lines = []
        for row in rows:
            prefix = "User" if row["role"] == "user" else "Assistant"
            lines.append(f"{prefix}: {row['content']}")

        return "\n".join(lines)

    # ── STATUS ─────────────────────────────────────────────────────────────

    def status(self) -> str:
        turns_in_buffer = len(self._buffer) // 2
        with _get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE session_id = ?",
                (self.session_id,)
            ).fetchone()[0]
        total_turns = total // 2
        return (f"Session '{self.session_id}' — "
                f"{turns_in_buffer} turns in buffer, "
                f"{total_turns} turns in database.")


# ── LONG-TERM SUMMARY FUNCTIONS ────────────────────────────────────────────
# These are called from main.py at session end and session start.
# The summary is generated by the LLM — not by dumping raw messages.

def save_summary(session_id: str, summary: str) -> None:
    """Save an LLM-generated summary for a session."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO summaries (session_id, summary, timestamp) VALUES (?, ?, ?)",
            (session_id, summary, now)
        )
        conn.commit()
    print(f"[Memory] Summary saved for session '{session_id}'.")


def load_latest_summary() -> str:
    """
    Load the most recent session summary from the database.
    Returns an empty string if no summary exists yet.
    Called at session start to inject long-term context into the system prompt.
    """
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT summary, session_id, timestamp FROM summaries "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if row:
        return (f"Previous session summary (session {row['session_id']}, "
                f"{row['timestamp']}):\n{row['summary']}")
    return ""


# ── SESSION UTILITIES ──────────────────────────────────────────────────────

def list_sessions() -> list[dict]:
    with _get_connection() as conn:
        rows = conn.execute("""
            SELECT
                session_id,
                MIN(timestamp) AS started,
                MAX(timestamp) AS last_active,
                COUNT(*) / 2   AS total_turns
            FROM conversations
            GROUP BY session_id
            ORDER BY last_active DESC
        """).fetchall()
    return [dict(row) for row in rows]


def delete_session(session_id: str) -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM summaries WHERE session_id = ?", (session_id,))
        conn.commit()
    print(f"[Memory] Session '{session_id}' deleted.")


def get_full_session(session_id: str) -> list[dict]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content, timestamp FROM conversations "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
    return [dict(row) for row in rows]