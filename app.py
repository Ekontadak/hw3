"""
app.py - Streamlit chat interface using new google-genai SDK
Run with: streamlit run app.py
"""

import os
import sys

import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.retrieval import retrieve, detect_categories
from src.memory import ConversationMemory, list_sessions
from src.ingestion import build_index

# ── PAGE CONFIG ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GW RAG Assistant",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── SETUP ──────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found. Add it to your .env file.")
    st.stop()

client       = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-3.1-flash-lite"
TOP_K        = 5

RAG_PROMPT = """You are a knowledgeable assistant specialising in
gravitational wave astronomy. Answer the question using ONLY the context
provided. Be precise with numbers. If the context does not contain enough
information, say so clearly.

Context:
{context}

Question: {question}
"""

# ── ENSURE INDEX ───────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Building knowledge base index...")
def load_index():
    chroma_dir = os.path.join(os.path.dirname(__file__), "chroma_db")
    if not os.path.exists(chroma_dir) or not os.listdir(chroma_dir):
        build_index()
    return True

load_index()

# ── SESSION STATE ──────────────────────────────────────────────────────────
if "memory"       not in st.session_state:
    st.session_state.memory       = ConversationMemory()
if "messages"     not in st.session_state:
    st.session_state.messages     = []
if "show_sources" not in st.session_state:
    st.session_state.show_sources = True

# ── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌊 GW Assistant")
    st.caption("Gravitational Wave RAG Pipeline")
    st.divider()

    memory = st.session_state.memory
    st.markdown(f"**Session:** `{memory.session_id}`")
    st.markdown(f"**Turns this session:** {len(st.session_state.messages) // 2}")
    st.divider()

    st.subheader("Settings")
    st.session_state.show_sources = st.toggle("Show retrieved sources", value=st.session_state.show_sources)
    top_k = st.slider("Chunks to retrieve", min_value=1, max_value=10, value=TOP_K)
    st.divider()

    st.subheader("Session")
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.memory.clear_buffer()
        st.rerun()
    if st.button("➕ New session", use_container_width=True):
        st.session_state.memory   = ConversationMemory()
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("Past sessions")
    sessions = list_sessions()
    if len(sessions) > 1:
        session_options = {
            f"{s['session_id']} ({s['total_turns']} turns)": s["session_id"]
            for s in sessions if s["session_id"] != memory.session_id
        }
        selected = st.selectbox("Resume a session", ["— select —"] + list(session_options.keys()))
        if selected != "— select —":
            sid = session_options[selected]
            if st.button("Load session", use_container_width=True):
                st.session_state.memory   = ConversationMemory(session_id=sid)
                st.session_state.messages = []
                st.rerun()
    else:
        st.caption("No past sessions yet.")

    st.divider()
    st.subheader("Knowledge base")
    st.caption("7 files · 2000+ chunks")
    st.caption("Model: " + GEMINI_MODEL)

# ── MAIN CHAT AREA ─────────────────────────────────────────────────────────
st.title("Gravitational Wave RAG Assistant")
st.caption("Ask anything about gravitational waves, LIGO, detections, or the event catalog.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if (msg["role"] == "assistant"
                and st.session_state.show_sources
                and msg.get("sources")):
            with st.expander(f"📎 Sources ({len(msg['sources'])} chunks)"):
                for i, chunk in enumerate(msg["sources"], 1):
                    meta     = chunk.get("metadata", {})
                    filename = meta.get("filename", "unknown")
                    category = meta.get("document_category", "unknown")
                    score    = chunk.get("rrf_score", 0)
                    source = meta.get("source", "")
                    st.markdown(f"**[{i}] {filename}** · `{category}` · score: `{score:.4f}`")
                    st.caption(f"Source: {source}")
                    st.caption(chunk.get("text", "")[:300] + "...")
                    if i < len(msg["sources"]):
                        st.divider()

# ── CHAT INPUT ─────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask about gravitational waves..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving context..."):
            chunks = retrieve(prompt, top_k=top_k)
            cats   = detect_categories(prompt)

        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            meta     = chunk.get("metadata", {})
            filename = meta.get("filename", "unknown")
            text     = chunk.get("text", "")
            context_parts.append(f"[{i}] Source: {filename}\n{text}")
        context = "\n\n---\n\n".join(context_parts) if context_parts else "No context found."

        with st.spinner("Thinking..."):
            gemini_prompt = RAG_PROMPT.format(context=context, question=prompt)

            # Build contents with history.
            contents = []
            for msg in st.session_state.memory.get_history():
                contents.append(
                    types.Content(
                        role=msg["role"],
                        parts=[types.Part(text=msg["parts"][0])]
                    )
                )
            contents.append(
                types.Content(role="user", parts=[types.Part(text=gemini_prompt)])
            )

            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                )
                answer = response.text.strip()
            except Exception as e:
                answer = f"API error: {e}"

        st.markdown(answer)

        if st.session_state.show_sources and chunks:
            with st.expander(f"📎 Sources ({len(chunks)} chunks · categories: {', '.join(cats)})"):
                for i, chunk in enumerate(chunks, 1):
                    meta     = chunk.get("metadata", {})
                    filename = meta.get("filename", "unknown")
                    category = meta.get("document_category", "unknown")
                    score    = chunk.get("rrf_score", 0)
                    source = meta.get("source", "")
                    st.markdown(f"**[{i}] {filename}** · `{category}` · score: `{score:.4f}`")
                    st.caption(f"Source: {source}")
                    st.caption(chunk.get("text", "")[:300] + "...")
                    if i < len(chunks):
                        st.divider()

    st.session_state.memory.add_turn(prompt, answer)
    st.session_state.messages.append({
        "role":    "assistant",
        "content": answer,
        "sources": chunks,
    })