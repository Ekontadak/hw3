"""
src/evaluate.py

Runs the full RAG pipeline against a set of question-answer pairs,
then uses Gemini as a judge to score each answer on a 0.0-1.0 scale.

This is called "LLM-as-a-Judge" - instead of string-matching the output
against a ground truth, we ask a language model to evaluate how good
the answer is across three dimensions: Faithfulness, Answer Relevance,
and Context Precision. This handles paraphrasing and partial answers gracefully.

The judge uses temperature=0 so its scores are deterministic -
running the evaluation twice gives the same scores.

Usage:
    python -m src.evaluate
    python -m src.evaluate --verbose      # print each answer in full

Quota info:
    Makes exactly 32 API calls (2 per question x 16 questions).
    7 second pause after every call = ~8 calls/min (gemini-3.1-flash-lite limit: 15/min).
    Total runtime: approximately 4-5 minutes (32 calls x 7s = ~4 min).
"""

import os
import sys
import json
import time
from collections import defaultdict

from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.retrieval import retrieve
from src.memory import ConversationMemory

# ── SETUP ──────────────────────────────────────────────────────────────────
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
load_dotenv(".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env")
    sys.exit(1)

client         = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL   = "gemini-3.1-flash-lite"
TOP_K          = 5
PASS_THRESHOLD = 0.5   # score in [0, 1] — pass if >= 0.5

# Pause after EVERY individual API call.
# 7 seconds = ~8 calls/min, safely under gemini-3.1-flash-lite limit of 15/min.
# This guarantees the full eval finishes in ~5 minutes
# and never exceeds the per-minute quota.
API_CALL_DELAY = 7

EVAL_PATH = os.path.join(os.path.dirname(__file__), "..", "eval_dataset.jsonl")


# ── SAFE API CALL ──────────────────────────────────────────────────────────
# All Gemini calls go through this function.
# It sleeps after every call and fails fast on quota errors
# rather than retrying (retrying a fully exhausted quota just wastes time).

def call_gemini(contents, temperature: float = None) -> str:
    try:
        config = types.GenerateContentConfig(temperature=temperature) if temperature is not None else None
        kwargs = {"model": GEMINI_MODEL, "contents": contents}
        if config:
            kwargs["config"] = config

        response = client.models.generate_content(**kwargs)
        answer   = response.text.strip()
    except Exception as e:
        answer = f"[API_ERROR: {e}]"
    finally:
        # Always sleep after a call, whether it succeeded or failed.
        time.sleep(API_CALL_DELAY)

    return answer


# ── RAG PROMPT ─────────────────────────────────────────────────────────────
RAG_PROMPT = """You are a knowledgeable assistant specialising in
gravitational wave astronomy. Answer the question using ONLY the context
provided. Be precise with numbers. If the context does not contain enough
information, say so clearly.

Context:
{context}

Question: {question}
"""


# ── JUDGE PROMPT ───────────────────────────────────────────────────────────
JUDGE_PROMPT = """You are an expert evaluator assessing the quality of an
AI assistant's answer to a question about gravitational wave astronomy.

Evaluate the GENERATED ANSWER on three dimensions, each scored 0.0 to 1.0:

1. Faithfulness — Is the answer grounded in the retrieved context?
   Does it avoid hallucinating facts not present in the context?
   (1.0 = fully grounded, 0.0 = fabricated or contradicts context)

2. Answer Relevance — Does the answer actually address the question asked?
   Is it complete and on-topic?
   (1.0 = fully addresses the question, 0.0 = completely off-topic or refused)

3. Context Precision — Was the right information retrieved?
   Could the answer be derived from the context provided?
   (1.0 = context contains everything needed, 0.0 = context is irrelevant)

Question:
{question}

Ground Truth Answer:
{ground_truth}

Generated Answer:
{generated_answer}

Respond ONLY with a JSON object, no extra text:
{{
  "faithfulness": <float 0.0-1.0>,
  "answer_relevance": <float 0.0-1.0>,
  "context_precision": <float 0.0-1.0>,
  "score": <average of the three, float 0.0-1.0>,
  "reason": "<one or two sentences explaining the score>"
}}
"""


# ── RAG PIPELINE ───────────────────────────────────────────────────────────
# Retrieves chunks and generates an answer. One API call total.

def run_rag(question: str, memory: ConversationMemory) -> tuple[str, list[dict]]:
    chunks = retrieve(question, top_k=TOP_K)
    if not chunks:
        return "No relevant context found in the knowledge base.", []

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta     = chunk.get("metadata", {})
        filename = meta.get("filename", "unknown")
        text     = chunk.get("text", "")
        context_parts.append(f"[{i}] Source: {filename}\n{text}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = RAG_PROMPT.format(context=context, question=question)

    # Build contents list with conversation history.
    contents = []
    for msg in memory.get_history():
        contents.append(
            types.Content(
                role=msg["role"],
                parts=[types.Part(text=msg["parts"][0])]
            )
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=prompt)])
    )

    # One API call — delay handled inside call_gemini.
    answer = call_gemini(contents)
    return answer, chunks


# ── JUDGE ──────────────────────────────────────────────────────────────────
# Scores the generated answer against ground truth. One API call total.
# temperature=0 makes scoring deterministic.

def judge_answer(question: str, ground_truth: str, generated_answer: str) -> dict:
    # If the RAG call itself failed, don't waste a judge call.
    if generated_answer.startswith("[API_ERROR:"):
        return {
            "score": 0.0, "faithfulness": 0.0,
            "answer_relevance": 0.0, "context_precision": 0.0,
            "verdict": "FAIL",
            "reason": "RAG call failed — no answer to evaluate.",
        }

    prompt = JUDGE_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        generated_answer=generated_answer,
    )

    raw = call_gemini(prompt, temperature=0)

    if raw.startswith("[API_ERROR:"):
        return {
            "score": 0.0, "faithfulness": 0.0,
            "answer_relevance": 0.0, "context_precision": 0.0,
            "verdict": "FAIL",
            "reason": f"Judge call failed: {raw}",
        }

    # Strip markdown fences if Gemini wraps the JSON in them.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
        score  = float(result.get("score", 0.0))
        score  = max(0.0, min(1.0, score))   # clamp to [0, 1]
        verdict = "PASS" if score >= PASS_THRESHOLD else "FAIL"
        return {
            "score":             round(score, 3),
            "faithfulness":      round(float(result.get("faithfulness", 0.0)), 3),
            "answer_relevance":  round(float(result.get("answer_relevance", 0.0)), 3),
            "context_precision": round(float(result.get("context_precision", 0.0)), 3),
            "verdict":           verdict,
            "reason":            result.get("reason", "No reason provided."),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "score": 0.0, "faithfulness": 0.0,
            "answer_relevance": 0.0, "context_precision": 0.0,
            "verdict": "FAIL",
            "reason": f"Could not parse judge response: {raw[:100]}",
        }


# ── LOAD DATASET ───────────────────────────────────────────────────────────

def load_eval_dataset(path: str) -> list[dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# ── PRINT RESULT ───────────────────────────────────────────────────────────

def print_result(i: int, item: dict, result: dict, verbose: bool) -> None:
    icon = "+" if result["verdict"] == "PASS" else "-"
    print(f"\n[{i:02d}] [{icon}] Score: {result['score']:.3f} - {result['verdict']}")
    print(f"       Q: {item['question']}")
    print(f"       Source: {item['source_file']} ({item.get('document_category', '?')})")
    print(f"       F={result.get('faithfulness',0):.2f} "
          f"AR={result.get('answer_relevance',0):.2f} "
          f"CP={result.get('context_precision',0):.2f}")
    print(f"       Reason: {result.get('reason', '')}")
    if verbose:
        print(f"       Generated: {result.get('generated_answer', '')}")
        print(f"       Ground truth: {item['ground_truth_answer']}")


# ── DIAGNOSIS ──────────────────────────────────────────────────────────────
# Finds the lowest scoring result and explains likely causes.
# This is the "diagnose one failure" requirement from the assignment.

def diagnose_failure(results: list[dict], items: list[dict]) -> None:
    worst_idx    = min(range(len(results)), key=lambda i: results[i]["score"])
    worst_result = results[worst_idx]
    worst_item   = items[worst_idx]

    print("\n" + "=" * 60)
    print("FAILURE DIAGNOSIS")
    print("=" * 60)
    print(f"Question:    {worst_item['question']}")
    print(f"Score:       {worst_result["score"]:.3f} - {worst_result["verdict"]}")
    print(f"Source file: {worst_item['source_file']}")
    print(f"Category:    {worst_item.get('document_category', 'unknown')}")
    print(f"\nGround truth:\n  {worst_item['ground_truth_answer']}")
    print(f"\nGenerated answer:\n  {worst_result.get('generated_answer', 'N/A')}")
    print(f"\nJudge reasoning:\n  {worst_result.get('reason', 'N/A')}")

    chunks = worst_result.get("chunks", [])
    if chunks:
        print("\nTop retrieved chunks:")
        for i, chunk in enumerate(chunks[:3], 1):
            meta = chunk.get("metadata", {})
            print(f"  [{i}] {meta.get('filename')} "
                  f"(category: {meta.get('document_category')}) - "
                  f"{chunk['text'][:120]}...")
    else:
        print("\nNo chunks retrieved - possible retrieval failure.")

    print("\nLikely cause:")
    score = worst_result["score"]
    if score < 0.2:
        print("  Complete retrieval miss - the relevant chunks were not retrieved.")
        print("  Consider adding more keywords to CATEGORY_KEYWORDS in retrieval.py")
    elif score < 0.4:
        print("  Partial retrieval - some relevant chunks found but key facts missing.")
        print("  Consider increasing TOP_K or widening the category filter.")
    else:
        print("  Answer was partially correct. The model may have paraphrased")
        print("  in a way the judge penalised. Review the ground truth wording.")


# ── MAIN EVALUATION LOOP ───────────────────────────────────────────────────

def run_evaluation(verbose: bool = False) -> None:
    print("Loading evaluation dataset...")
    items = load_eval_dataset(EVAL_PATH)
    n     = len(items)
    print(f"  {n} questions loaded.")
    print(f"  Total API calls: {n * 2} ({n} RAG + {n} judge)")
    print(f"  Delay per call:  {API_CALL_DELAY}s")
    print(f"  Rate:            {60 // API_CALL_DELAY} calls/min (free tier limit: 15/min)")
    print(f"  Est. runtime:    ~{(n * 2 * API_CALL_DELAY) // 60 + 1} minutes\n")

    # Fresh memory session — no prior context bleeds into eval answers.
    memory  = ConversationMemory()
    results = []

    print("-" * 60)

    for i, item in enumerate(items, 1):
        question     = item["question"]
        ground_truth = item["ground_truth_answer"]

        print(f"\n[{i:02d}/{n}] Running: {question[:60]}...")

        # Step 1 — RAG (1 API call + 4s sleep inside call_gemini).
        generated, chunks = run_rag(question, memory)

        # Step 2 — Judge (1 API call + 4s sleep inside call_gemini).
        judgment = judge_answer(question, ground_truth, generated)

        result = {**judgment, "generated_answer": generated, "chunks": chunks}
        results.append(result)

        print_result(i, item, result, verbose)

    # ── final report ──
    scores     = [r["score"] for r in results]
    mean_score = sum(scores) / len(scores)
    passes     = sum(1 for r in results if r["verdict"] == "PASS")
    fails      = len(results) - passes
    accuracy_pct = mean_score * 100

    print("\n" + "=" * 60)
    print("EVALUATION REPORT")
    print("=" * 60)
    print(f"  Total questions : {n}")
    print(f"  Passed (>= {PASS_THRESHOLD}) : {passes}")
    print(f"  Failed (< {PASS_THRESHOLD})  : {fails}")
    print(f"  Mean score      : {mean_score:.3f} / 1.000")
    print(f"  Accuracy        : {accuracy_pct:.1f}%")

    print("\n  Average scores by dimension:")
    for dim in ("faithfulness", "answer_relevance", "context_precision"):
        avg = sum(r.get(dim, 0.0) for r in results) / n
        print(f"    {dim:<25} {avg:.3f}")

    print("\n  By document_category:")
    cat_scores = defaultdict(list)
    for item, result in zip(items, results):
        cat_scores[item.get("document_category", "unknown")].append(result["score"])
    for cat, cat_s in sorted(cat_scores.items()):
        avg = sum(cat_s) / len(cat_s)
        print(f"    {cat:<25} avg {avg:.3f} ({len(cat_s)} questions)")

    diagnose_failure(results, items)

    # Save full results to JSON for the README.
    out_path = os.path.join(os.path.dirname(__file__), "..", "eval_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "mean_score":   mean_score,
            "accuracy_pct": accuracy_pct,
            "pass_rate":    passes / n,
            "total":        n,
            "passes":       passes,
            "fails":        fails,
            "results": [
                {
                    "question":          items[i]["question"],
                    "source":            items[i]["source_file"],
                    "score":             results[i]["score"],
                    "faithfulness":      results[i].get("faithfulness", 0.0),
                    "answer_relevance":  results[i].get("answer_relevance", 0.0),
                    "context_precision": results[i].get("context_precision", 0.0),
                    "verdict":           results[i]["verdict"],
                    "reason":            results[i].get("reason", ""),
                }
                for i in range(n)
            ]
        }, f, indent=2)
    print(f"\n  Full results saved to eval_results.json")


# ── ENTRY POINT ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    verbose = "--verbose" in sys.argv
    run_evaluation(verbose=verbose)