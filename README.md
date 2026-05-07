# 🧑‍💼 RH Pre-selection Platform

An end-to-end HR pre-selection system combining CV extraction, candidate ranking, and AI-powered interview chatbot.

---

## Features

| | Feature | Description |
|---|---|---|
| 📄 | **CV Upload & Extraction** | Candidates upload a PDF; structured data is extracted via LLM + RapidAPI fallback and stored in MongoDB |
| 📊 | **CV Ranking** | HR enters a job description; candidates are ranked using semantic skill matching, experience, and education scoring |
| 🤖 | **Chatbot Interview** | Top candidates are interviewed by an AI chatbot (LangGraph + OpenRouter); results include scores, strengths/weaknesses, and a full transcript |

---

## Project Structure

```
merged_app/
├── app.py                  # Streamlit home page
├── api.py                  # FastAPI chatbot API (run separately)
├── .env                    # Environment variables (see .env.example)
├── requirements.txt
│
├── cv_extraction/          # CV parsing (LLM + RapidAPI + ChromaDB)
├── cv_ranking/             # Ranking (semantic similarity + scoring)
│
├── chatbot/
│   ├── config/             # OpenRouter LLM config + prompts
│   ├── graph/              # LangGraph graph builder
│   ├── models/             # Pydantic state + schema models
│   ├── nodes/              # Graph nodes (init, question gen, analysis, decision, evaluation)
│   ├── services/           # Session management
│   └── cv_adapter.py       # Converts extracted CV → chatbot input format
│
└── pages/
    ├── 1_Apply.py          # Candidate CV upload page
    ├── 2_Ranking.py        # HR ranking dashboard
    └── 3_Interview.py      # Chatbot interview page
```

---

## Setup

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/nour2003-coder/cv_analyzer_interview.git
cd cv_analyzer_interview
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `api_key`, `api_key2`, `api_key3` | OpenRouter keys for CV extraction |
| `OPENROUTER_API_KEY` | OpenRouter key for the chatbot |
| `OPENROUTER_MODEL` | Model to use (e.g. `meta-llama/llama-3.1-8b-instruct`) |
| `API_KEY`, `API_HOST`, `API_URL` | RapidAPI resume parser credentials |
| `MONGO_URI` | MongoDB connection string |
| `CHATBOT_API_URL` | URL where the FastAPI chatbot runs (default: `http://localhost:8001`) |

### 4. Run

Open two terminals (both with the venv activated):

```bash
# Terminal 1 — Streamlit UI
streamlit run app.py

# Terminal 2 — Chatbot API
uvicorn api:app --reload --port 8001
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Workflow

```
Candidate uploads CV (Apply page)
        ↓
HR enters job description → CVs ranked (Ranking page)
        ↓
HR clicks "Start Interview" on a candidate
        ↓
AI chatbot conducts interview axis by axis (Interview page)
        ↓
Full evaluation report: scores, strengths, weaknesses, recommendation
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| API | FastAPI + Uvicorn |
| Interview orchestration | LangGraph + LangChain |
| LLM provider | OpenRouter |
| Vector store | ChromaDB + HuggingFace Embeddings |
| Semantic matching | sentence-transformers |
| Database | MongoDB |
| CV parsing fallback | RapidAPI |
| PDF reports | ReportLab |
