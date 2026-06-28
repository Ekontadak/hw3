# Gravitational Wave Astronomy RAG Pipeline

---

## 1. Domain & Dataset

### 1.1 Domain

The knowledge base covers **Gravitational Wave Astronomy**, the scientific field concerned with the detection,
analysis, and astrophysical interpretation of gravitational waves using ground-based laser interferometer
observatories. The domain spans five distinct layers:

| Layer | Description |
|---|---|
| **Physics** | What gravitational waves are, how they propagate, and what produces them |
| **Instrumentation** | How LIGO, Virgo, and KAGRA interferometers work at an engineering level |
| **Pipeline software** | The matched-filter search algorithms that identify candidate events in raw detector data |
| **Event catalog** | The structured database of all confirmed and candidate detections to date |
| **Observing runs** | The operational history of the detector network from O1 through O4b |

---

### 1.2 Corpus Files

#### PDF — GW150914 Detection Paper

| Attribute             | Value |
|-----------------------|---|
| **Filename**          | `gw150914_detection.pdf` |
| **Source**            | Abbott et al. (LIGO Scientific, Virgo), *Phys. Rev. Lett.* **116**, 061102 (2016). arXiv:1602.03837 |
| **Author(s)**         | B.P. Abbott et al. (LIGO Scientific Collaboration and Virgo Collaboration) |
| **document_category** | `detection_research` |
| **Obtained from**     | Downloaded directly from arXiv (https://arxiv.org/abs/1602.03837) |

**Content:** The primary scientific paper announcing the first direct detection of gravitational waves on
September 14, 2015. Covers the astrophysical properties of GW150914 (binary black hole merger at ~410 Mpc,
component masses ~36 and ~29 solar masses), the significance of the detection, tests of general relativity,
and the implications for black hole astrophysics.

**Questions it enables:**
- What were the component masses of GW150914?
- How far away was the source of GW150914?
- What was the statistical significance of the first detection?
- How did the observed waveform compare to general relativity predictions?
- What is the estimated final black hole mass after merger?

---

#### Markdown — GW Detection Pipelines

| Attribute | Value |
|---|---|
| **Filename** | `gw_detection_pipelines.md` |
| **Source** | Compiled and curated from 8 primary papers (see references within the file) |
| **Author(s)** | Content sourced from Usman et al. 2016, Messick et al. 2017, Sachdev et al. 2019, Aubin et al. 2021, Veitch et al. 2015, Ashton et al. 2019 |
| **document_category** | `analysis_software` |
| **Obtained from** | Written as a synthesis document; every factual claim verified against the cited papers |

**Content:** A technical reference document explaining the full gravitational wave detection pipeline from
raw strain data to astrophysical inference. Covers data conditioning (calibration, data quality vetoes, PSD
estimation), the matched-filter SNR formula, template bank construction (3% mismatch criterion), the three
active search pipelines (PyCBC, GstLAL, MBTA) with their key design differences, false-alarm rate estimation,
and Bayesian parameter estimation frameworks (LALInference, Bilby).

**Questions it enables:**
- What is the SNR formula used in matched filtering?
- How does PyCBC's exact-match coincidence test work?
- What is the purpose of the chi-squared signal consistency test?
- How does GstLAL differ from PyCBC in its filtering approach?
- How early before merger can GstLAL issue an alert for a binary neutron star?
- What is the maximum template bank mismatch in the PyCBC search?
- What sampler does Bilby use for parameter estimation?

---

#### JSON (1) — GWTC Event Catalog Metadata

| Attribute             | Value |
|-----------------------|---|
| **Filename**          | `gwtc_catalog.json` |
| **Source**            | GWOSC Public API v2 (https://gwosc.org/api/v2/event-versions) |
| **Author(s)**         | LIGO-Virgo-KAGRA Collaboration / Gravitational Wave Open Science Center |
| **document_category** | `event_catalog` |
| **Obtained from**     | Downloaded via browser from `https://gwosc.org/api/v2/event-versions?format=json&lastver=true&pagesize=500`. The `lastver=true` parameter returns only the most recent version of each event. |

**Content:** 433 gravitational wave event records (latest version per event) spanning GWTC-1 through GWTC-5.0
and all O4 discovery papers. Each record contains: `name`, `shortName`, `gps` timestamp, `version`, `catalog`,
`detectors` (list of observatories that contributed data), `doi`, and `detail_url`. Does not contain
astrophysical parameters, those are in the XLSX file.

**Questions it enables:**
- Which detectors observed GW170817?
- What catalog does GW190814 belong to?
- How many events are in the GWTC-5.0 catalog?
- What is the GPS timestamp of GW150914?
- Which events were observed by all three detectors H1, L1, and V1?
- What is the DOI for the GWTC-3 data release?

---

#### JSON (2) — Observing Run Summaries

| Attribute             | Value |
|-----------------------|---|
| **Filename**          | `observing_runs.json` |
| **Source**            | GWOSC data release pages (https://gwosc.org/data/, https://gwosc.org/O4/O4a, https://gwosc.org/O4/O4b) |
| **Author(s)**         | GWOSC — all dates, GPS times, and detector lists verified directly against GWOSC pages |
| **document_category** | `observing_runs` |
| **Obtained from**     | Manually compiled from GWOSC data release pages fetched directly. GPS start/end times taken verbatim from the O4a and O4b release pages. O1–O3 GPS values computed from timeline URL parameters on gwosc.org/data/. |

**Content:** Structured summary of 6 observing runs (O1, O2, O3a, O3b, O4a, O4b) with: official start/end
dates, GPS timestamps, calendar duration in days, detector network configuration per run, notable events,
and contextual notes about each run's scientific significance and operational history.

**Questions it enables:**
- When did O3b end and why?
- Which detectors were online during O4a?
- What is the GPS start time of O2?
- How long did O3a last?
- Was Virgo operational during O4a?
- Which observing run first included three detectors simultaneously?

---

#### XLSX — GW Event Parameters Table

| Attribute | Value |
|---|---|
| **Filename** | `gw_events.xlsx` |
| **Source** | GWOSC Event API with `include-default-parameters=true` (https://gwosc.org/api/v2/event-versions) |
| **Author(s)** | LIGO-Virgo-KAGRA Collaboration / Gravitational Wave Open Science Center |
| **document_category** | `event_parameters` |
| **Obtained from** | Downloaded from the GWOSC event API with default parameters included, saved as `.xlsx`. Contains the same 433 events as the JSON catalog but in flat tabular form with astrophysical parameters expanded into columns. |

**Content:** Flat table of 433 GW events with full parameter columns: `mass_1_source`, `mass_2_source`,
`chirp_mass_source`, `total_mass_source`, `final_mass_source` (all in solar masses), `luminosity_distance`
(Mpc), `redshift`, `network_matched_filter_snr`, `far` (false alarm rate in yr⁻¹), `p_astro`, `chi_eff`
, all with corresponding upper and lower 90% credible interval columns.

**Questions it enables:**
- What is the chirp mass of GW190814?
- Which event has the highest network SNR?
- What is the luminosity distance of GW170817?
- Which binary black hole merger produced the most massive final black hole?
- What is the effective spin parameter of GW150914?
- Which events have a false alarm rate below 1 per million years?

---

#### HTML (1) — LIGO: All About Gravitational Waves

| Attribute | Value |
|---|---|
| **Filename** | `ligo_learn_more.html` |
| **Source** | LIGO Laboratory, Caltech — "Learn More" educational section (ligo.caltech.edu) |
| **Author(s)** | LIGO Laboratory, California Institute of Technology and MIT. Supported by NSF Award PHY-2309200. |
| **document_category** | `educational_explainer` |
| **Obtained from** | Five subpages fetched directly and compiled into a single HTML file: `what-are-gw`, `gw-sources`, `why-detect-gw`, `ligo-technology`, and `observatories-collaborations`. Navigation chrome stripped; substantive content preserved in full. |

**Content:** Educational overview covering: (1) what gravitational waves are and Einstein's 1916 prediction,
(2) the four source types , compact binary inspiral, continuous, stochastic, and burst, (3) the scientific
motivation for detecting gravitational waves, (4) LIGO's core engineering technologies (seismic isolation,
quad suspensions, ultra-high vacuum, precision laser), and (5) the global detector network including Virgo,
KAGRA, GEO600, and the planned LIGO-India.

**Questions it enables:**
- What are the four types of gravitational waves LIGO searches for?
- How does LIGO's seismic isolation system work?
- Why can gravitational waves carry information that electromagnetic radiation cannot?
- How many times does the laser bounce inside a LIGO arm before recombination?
- What is the atmospheric pressure inside LIGO's vacuum tubes?
- What is the role of the beam splitter in LIGO's interferometer?
- What is LIGO-India and what will it improve?

---

#### HTML (2) — Wikipedia: Gravitational Wave

| Attribute | Value |
|---|---|
| **Filename** | `GW_wikipedia.html` |
| **Source** | Wikipedia, *Gravitational wave*, en.wikipedia.org/wiki/Gravitational_wave |
| **Author(s)** | Wikipedia contributors. Licensed under CC BY-SA 4.0. |
| **document_category** | `educational_explainer` |
| **Obtained from** | Full article text extracted from a browser save of the Wikipedia page and wrapped in clean HTML. All citation brackets, navigation chrome, language links, and sidebar elements removed. Substantive article text preserved verbatim. |

**Content:** The complete Wikipedia article on gravitational waves covering: full history from Heaviside
(1893) and Poincaré (1905) through Einstein's 1916 prediction, Eddington's coordinate-system doubts,
Feynman's sticky bead argument (1957), Weber bars, and the Hulse–Taylor binary pulsar (1974); wave
properties (amplitude h ~ 10⁻²¹, frequency, wavelength, speed c, plus/cross polarization 45° apart);
all source types including the orbital decay formula, compact binaries, supernovae, spinning neutron star
"mountains" (<10 cm), and primordial GWs; properties including gravitational recoil kicks up to 4000 km/s;
the graviton and quantum gravity; the full detection hierarchy from Weber bars and MiniGRAIL through
ground-based interferometers, Einstein@Home, LISA, and all 7 active pulsar timing array projects
(NANOGrav, PPTA, EPTA, InPTA, MPTA, APT, CPTA); detailed accounts of GW150914 and GW170817; and the
2023 gravitational wave background announcement.

**Questions it enables:**
- Who first proposed gravitational waves before Einstein?
- What was Feynman's sticky bead argument?
- Why did Einstein briefly believe gravitational waves could not exist?
- What is the maximum recoil kick velocity after two supermassive black holes merge?
- How tall are the "mountains" on a spinning neutron star that cause it to emit gravitational waves?
- What is the Hellings-Downs curve and what did the 2023 PTA results show?
- How does LISA differ from ground-based detectors in its target frequency range?
- What was the BICEP2 claim and why was it retracted?
- How many pulsar timing array projects are currently active globally?
- What were the neutron star masses measured in GW170817?

---

### 1.3 Coverage Summary

| `document_category` | Files | Primary use in RAG |
|---|---|---|
| `detection_research` | `gw150914_detection.pdf` | Specific event data, GR tests, waveform properties |
| `analysis_software` | `gw_detection_pipelines.md` | Pipeline mechanics, algorithm details, PE methods |
| `event_catalog` | `gwtc_catalog.json` | Event lookup by name, catalog, detector, timestamp |
| `observing_runs` | `observing_runs.json` | Run-level metadata — dates, detectors, duration |
| `event_parameters` | `gw_events.xlsx` | Numerical parameter lookup across all 433 events |
| `educational_explainer` | `ligo_learn_more.html`, `GW_wikipedia.html` | Conceptual, historical, and engineering questions |

The two `educational_explainer` HTML files are complementary rather than redundant. The LIGO file focuses
on engineering depth (seismic isolation, vacuum specs, laser design) and source taxonomy from an
observatory perspective. The Wikipedia file provides the full historical narrative, wave physics formalism,
the complete detection technology landscape (Weber bars through PTAs), and the broader astrophysical
context. Together they cover questions that neither file alone could answer.

No two files cover the same content at the same level of detail. The corpus spans from engineering
specifications (HTML, MD) through structured numerical data (XLSX, JSON) to primary scientific literature
(PDF), ensuring that the retrieval and metadata filtering components of the pipeline are exercised across
meaningfully distinct document categories.

---

## 2. Ingestion & Filtering

### 2.1 Parsing Strategy

All files in `data/` are processed by `src/ingestion.py`. The `route_and_parse(filepath)`
function dispatches each file to a dedicated parser based on filename:

| File type | Parser | Library |
|---|---|---|
| `.pdf` | `parse_pdf` | `pdfplumber` — extracts text layer page by page |
| `.md` | `parse_markdown` | plain `open()` + `read()` |
| `.html` | `parse_html` | `BeautifulSoup` — strips scripts, styles, nav before extracting text |
| `gwtc_catalog.json` | `parse_json_catalog` | `json` — serialises each of 433 events as a key-value string |
| `observing_runs.json` | `parse_json_runs` | `json` — serialises each of 6 runs as a key-value string |
| `.xlsx` | `parse_xlsx` | `pandas` — each row becomes one text chunk |

### 2.2 Chunking

Text-based files (PDF, Markdown, HTML) are split into overlapping windows after parsing:

- **Chunk size:** 800 characters
- **Overlap:** 150 characters
- **Rationale:** 800 characters fits roughly 150–200 tokens, well within the embedding
  model's 256-token limit. The 150-character overlap prevents sentences that straddle
  a chunk boundary from being lost.

Structured files (JSON, XLSX) are **pre-chunked** , each record (event, run, row) becomes
its own chunk without further splitting. This ensures individual events are always
retrievable as complete units and never split across two chunks.

### 2.3 Metadata Schema

Every chunk stored in ChromaDB carries the following metadata fields:

| Field | Example | Purpose |
|---|---|---|
| `document_category` | `event_parameters` | Pre-filter target for retrieval |
| `source` | `gwosc.org/api/v2/...` | Provenance for citation |
| `author` | `LIGO-Virgo-KAGRA Collaboration` | Attribution |
| `filename` | `gw_events.xlsx` | Trace chunk back to source file |
| `event_name` | `GW150914` | (JSON/XLSX only) enables per-event filtering |
| `run` | `O4a` | (observing_runs.json only) enables per-run filtering |

### 2.4 Metadata Pre-Filtering

`src/retrieval.py` analyses each query for keywords before the vector search runs.
It assigns one or more `document_category` values and passes them to ChromaDB as a
`where` clause:

```python
collection.query(
    query_texts=[query],
    where={"document_category": {"$in": ["event_parameters", "event_catalog"]}},
    n_results=20,
)
```

This means a question about masses only searches the ~433 event parameter chunks, not
the 2000+ chunks in the full index. The category detection uses keyword matching:

| Query keywords | Categories searched |
|---|---|
| mass, chirp, distance, snr, redshift | `event_parameters` |
| catalog, detector, H1, L1, V1, GPS | `event_catalog` |
| O1, O2, O3, O4, observing run, duration | `observing_runs` |
| pipeline, PyCBC, GstLAL, matched filter | `analysis_software` |
| GW150914, first detection, confidence | `detection_research` |
| what is, how does, history, interferometer | `educational_explainer` |
| any GW event name (e.g. GW170817) | `event_parameters` + `event_catalog` |

Each category has more keywords than shown here. If no keywords match, all categories are searched so no query returns empty results.

### 2.5 Hybrid Retrieval

The retriever combines two ranking signals with Reciprocal Rank Fusion (RRF):

**Dense retrieval** , the query is embedded with `all-MiniLM-L6-v2` and compared
against chunk embeddings using cosine similarity. Captures semantic similarity
("how heavy is the merger" → matches `mass_1_source`).

**BM25** , classical keyword frequency scoring over the dense candidates. Captures
exact matches that dense search can miss (`GW150914`, `chi_eff`, `O3b`).

**RRF fusion** , combines both ranked lists using:

```
RRF_score(d) = 1/(k + rank_dense) + 1/(k + rank_bm25)    k = 60
```

The document ranked highly in both lists wins. The final top-K chunks are passed
to the language model as context.

---

## 3. Memory Architecture

### 3.1 Overview

Conversation memory is managed by `src/memory.py` using a two-level architecture:

```
┌─────────────────────────────────┐
│         Short-term Buffer       │  ← in RAM, last 6 turns
│   [user, model, user, model...] │    passed to Gemini on every call
└────────────────┬────────────────┘
                 │ every turn written
                 ▼
┌─────────────────────────────────┐
│       Long-term SQLite DB       │  ← persists forever
│   memory.db · conversations     │    survives restarts
│   memory.db · summaries         │    LLM-generated session summaries
└─────────────────────────────────┘
```

### 3.2 Short-Term Buffer

- Holds the last **6 turns** (12 messages: 6 user + 6 model) in RAM
- Passed to Gemini as conversation history on every call
- Gives the model conversational context , follow-up questions like
  "what about the second one?" resolve correctly
- Trimmed automatically when it exceeds 6 turns; oldest turns are dropped

### 3.3 Long-Term SQLite Database

Every turn is written to `memory.db` immediately after it occurs:

```sql
CREATE TABLE conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,   -- 'user' or 'model'
    content     TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL
)
```

At session end, the full conversation is passed to the LLM which generates a concise summary
(3–5 sentences) stored in a separate table:

```sql
CREATE TABLE summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    summary     TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL
)
```

The most recent summary is loaded at the start of every new session and injected into the
system prompt so the assistant has context from previous sessions.

**Key distinction between the two layers:**

- **Short-term**: raw message history, exact turns, volatile. Used to maintain coherence
  within a single session (e.g. resolving pronouns in follow-up questions).
- **Long-term**: LLM-generated compressed summary, persisted to disk. Used to personalise
  the assistant across sessions. Raw history is never dumped verbatim , the LLM summarises
  it before saving, preventing context window bloat.

### 3.4 Session Lifecycle

```bash
python main.py              # new session, fresh session_id
python main.py a01372bf     # resume session a01372bf from DB
```

In the Streamlit UI, sessions can be resumed from the sidebar dropdown.
Via the API, pass `conversation_id` in the `POST /message` request body.

---

## 4. Evaluation Results

### 4.1 Methodology

Evaluation is performed by `src/evaluate.py` using the **LLM-as-a-Judge** approach:

1. Each of the 16 questions in `eval_dataset.jsonl` is run through the full
   retrieval + generation pipeline
2. The generated answer, ground truth answer, and original question are passed
   to a separate Gemini call configured at `temperature=0`
3. The judge scores the generated answer on three dimensions, each in [0, 1]:

| Dimension | Description |
|---|---|
| **Faithfulness** | Is the answer grounded in the retrieved context? Does it avoid hallucinating facts not present in the context? |
| **Answer Relevance** | Does the answer actually address the question? Is it complete and on-topic? |
| **Context Precision** | Was the right information retrieved? Could the answer be derived from the context provided? |

The final score is the average of the three dimensions, also in [0, 1]. Pass threshold: score ≥ 0.5.
Temperature=0 ensures scores are deterministic , running the evaluation twice gives the same scores.

### 4.2 Evaluation Dataset

16 questions across all 6 document categories:

| # | Question | Source file | Category |
|---|---|---|---|
| 1 | What is the chirp mass of GW150914? | `gw_events.xlsx` | `event_parameters` |
| 2 | Which detectors observed GW170817? | `gwtc_catalog.json` | `event_catalog` |
| 3 | What catalog does GW190814 belong to? | `gwtc_catalog.json` | `event_catalog` |
| 4 | What is the GPS timestamp of GW150914? | `gwtc_catalog.json` | `event_catalog` |
| 5 | What is the luminosity distance of GW170817? | `gw_events.xlsx` | `event_parameters` |
| 6 | Which detectors were online during O4a? | `observing_runs.json` | `observing_runs` |
| 7 | When did O3b end and why? | `observing_runs.json` | `observing_runs` |
| 8 | What were the component masses of GW150914? | `gw150914_detection.pdf` | `detection_research` |
| 9 | What was the statistical confidence of GW150914? | `gw150914_detection.pdf` | `detection_research` |
| 10 | What are the four types of gravitational waves? | `ligo_learn_more.html` | `educational_explainer` |
| 11 | How does LIGO's quad suspension reduce vibrations? | `ligo_learn_more.html` | `educational_explainer` |
| 12 | How does GstLAL differ from PyCBC? | `gw_detection_pipelines.md` | `analysis_software` |
| 13 | What is the purpose of the chi-squared test? | `gw_detection_pipelines.md` | `analysis_software` |
| 14 | What was Feynman's sticky bead argument? | `GW_wikipedia.html` | `educational_explainer` |
| 15 | What is the GPS start time of O4b? | `observing_runs.json` | `observing_runs` |
| 16 | How many gravitational wave events are in the total catalog? | `gwtc_catalog.json` | `event_catalog` |

6 of the 16 questions (Q1, Q2, Q4, Q5, Q10, Q16) require data from JSON or XLSX files.

### 4.3 Results

The evaluation was run using `gemini-3.1-flash-lite` as both the RAG model and the LLM judge
(`temperature=0`). Each answer is scored on three dimensions, Faithfulness, Answer Relevance,
and Context Precision, each in [0, 1], with the final score being their average.
The full results are saved to `eval_results.json`.

| Metric | Value |
|---|---|
| Total questions | 16 |
| Passed (≥ 0.5) | 16 |
| Failed (< 0.5) | 0 |
| Mean score | 0.938 / 1.000 |
| Accuracy | **93.8%** |

**Average scores by dimension:**

| Dimension | Score |
|---|---|
| Faithfulness | 0.969 |
| Answer Relevance | 0.969 |
| Context Precision | 0.875 |

**By document category:**

| Category | Avg Score | Questions |
|---|---|---|
| `observing_runs` | 0.990 | 3 |
| `educational_explainer` | 0.967 | 3 |
| `event_parameters` | 0.965 | 2 |
| `analysis_software` | 0.935 | 2 |
| `event_catalog` | 0.917 | 4 |
| `detection_research` | 0.835 | 2 |

### 4.4 Failure Diagnosis

The lowest-scoring question was **Q9** with a score of **0.670**:

> *"What was the statistical confidence of the GW150914 detection?"*

**Ground truth:** The confidence level of GW150914 being a real gravitational wave detection
was 99.99994%, corresponding to a significance of 5.1 sigma.

**Generated answer:** *"The provided context does not contain information regarding the
statistical confidence of the GW150914 detection."*

**Dimension scores:**

| Dimension | Score |
|---|---|
| Faithfulness | 1.000 |
| Answer Relevance | 1.000 |
| Context Precision | 0.000 |

**Diagnosis: Retrieval failure, not an LLM hallucination.**

The model answered correctly given what it received: it truthfully reported that the context
did not contain the answer. The problem was upstream in the retrieval step. Instead of pulling
the relevant section of `gw150914_detection.pdf` where the 5.1 sigma figure appears, the
retriever returned catalog JSON chunks and XLSX parameter rows for GW150914.

The distinction is important:

- A **hallucination** would mean the right chunk was retrieved but the model fabricated an answer.
- A **retrieval failure** means the right chunk was never fetched, confirmed here by Context Precision = 0.0.

**Fix:** The query "statistical confidence of GW150914" matched both `detection_research`
and `event_catalog` categories due to the event name. The event-name filter in `dense_search`
then targeted both the catalog JSON and XLSX chunks for GW150914, but the confidence figure
only exists in the PDF prose, not in any structured metadata field. A targeted fix would be
to add `"statistical confidence"` and `"sigma"` as high-priority keywords that exclusively
map to `detection_research`, or alternatively increase `TOP_K` so more PDF chunks are
included in the context alongside the structured data chunks.

---

## 5. Execution Instructions

### 5.1 Prerequisites

```bash
# Python 3.10+
python --version

# Clone the repo and enter the project
cd ~/PycharmProjects/hw3

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows

# Install all dependencies
pip install -r requirements.txt
```

### 5.2 Environment Setup

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

Get a free API key at [aistudio.google.com](https://aistudio.google.com).

### 5.3 Build the Index

Run once to parse all files in `data/` and build the ChromaDB vector index.
This takes approximately 1–2 minutes on first run.

```bash
python -m src.ingestion
```

To force a full rebuild (e.g. after changing a data file):

```bash
python -m src.ingestion --rebuild
```

### 5.4 Run the CLI Chatbot

```bash
# Start a new session
python main.py

# Resume a previous session
python main.py <session_id>        # e.g. python main.py a01372bf
```

**Available commands during chat:**

| Command | Action |
|---|---|
| `quit` or `exit` | End the session and generate a long-term summary |
| `status` | Show memory buffer info and session ID |
| `clear` | Wipe the short-term buffer without ending the session |

### 5.5 Run the Streamlit UI (Bonus A)

```bash
streamlit run app.py
```

Opens automatically at `http://localhost:8501`. Features:
- Full chat interface with message history
- Collapsible source panel showing retrieved chunks, `document_category`, `source` metadata, and RRF scores
- Session management in the sidebar (new session, resume past session)
- Chunk count slider and sources toggle

### 5.6 Run the FastAPI Backend (Bonus B)

```bash
uvicorn src.api:app --reload --port 8000
```

Interactive API docs: `http://localhost:8000/docs`

**Example API calls:**

```bash
# Start a new conversation
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"user_message": "What is the chirp mass of GW150914?"}'

# Continue the same conversation
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"user_message": "And how far away was it?", "conversation_id": 1}'

# List all conversations
curl http://localhost:8000/conversations

# Get full history of a conversation
curl http://localhost:8000/conversation/1

# Delete a conversation
curl -X DELETE http://localhost:8000/conversation/1
```

### 5.7 Run the Evaluation

```bash
# Standard run — scores all 16 questions
python -m src.evaluate

# Verbose run — also prints full generated answers
python -m src.evaluate --verbose
```

Results are printed to the console and saved to `eval_results.json`.

### 5.8 Project File Structure

```
hw3/
├── data/
│   ├── gw150914_detection.pdf       detection paper (Abbott et al. 2016)
│   ├── gw_detection_pipelines.md    pipeline software reference
│   ├── gwtc_catalog.json            433 events — catalog metadata
│   ├── observing_runs.json          O1–O4b run summaries
│   ├── gw_events.xlsx               433 events — physics parameters
│   ├── ligo_learn_more.html         LIGO Caltech educational pages
│   └── GW_wikipedia.html            Wikipedia gravitational wave article
├── src/
│   ├── __init__.py
│   ├── ingestion.py                 parse, chunk, embed, store
│   ├── retrieval.py                 dense + BM25 + RRF hybrid search
│   ├── memory.py                    short-term buffer + long-term summaries
│   ├── evaluate.py                  LLM-as-a-Judge evaluation pipeline
│   └── api.py                       FastAPI REST backend (Bonus B)
├── app.py                           Streamlit chat UI (Bonus A)
├── main.py                          CLI conversational loop
├── eval_dataset.jsonl               16 QA pairs with ground truth
├── eval_results.json                generated after running evaluate.py
├── memory.db                        SQLite conversation history
├── chroma_db/                       ChromaDB vector index (committed to repo)
├── .env                             API keys (not committed)
├── requirements.txt
└── README.md
```

### 5.9 .gitignore

```
memory.db
eval_results.json
.env
__pycache__/
*.pyc
.venv/
*.egg-info/
```

---

## 6. Bonus Features

### Streamlit Chat Interface (`app.py`)

A browser-based chat UI built with Streamlit. Run with `streamlit run app.py`.

**Features beyond the CLI:**
- Visual chat bubbles with message history persisted across reruns
- Collapsible source expander under each answer showing chunk text,
  `filename`, `document_category`, `source` citation, and RRF score
- Sidebar with session controls — new session, clear buffer, resume past sessions
- Adjustable chunk count slider (1–10)
- Sources toggle to hide/show retrieved context

### FastAPI Episodic Memory Backend (`src/api.py`)

A REST API that exposes the full RAG pipeline and memory system over HTTP.
Run with `uvicorn src.api:app --reload --port 8000`.

Database schema:

```sql
CREATE TABLE Conversations (id INTEGER PRIMARY KEY, created_at TEXT, title TEXT)
CREATE TABLE Messages (id INTEGER PRIMARY KEY, conversation_id INTEGER FK, role TEXT, content TEXT, timestamp TEXT)
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/conversations` | List all conversation threads |
| `GET` | `/conversation/{id}` | Retrieve a specific thread's history |
| `POST` | `/message` | Store a new user/AI message pair |
| `DELETE` | `/conversation/{id}` | Delete a thread and its messages |
| `GET` | `/health` | Server health check |

Auto-generated interactive docs available at `http://localhost:8000/docs`.