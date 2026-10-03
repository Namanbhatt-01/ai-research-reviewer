# 🔬 AI System to Automatically Review and Summarize Research Papers

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-FF4F00?logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![PyMuPDF4LLM](https://img.shields.io/badge/Parser-PyMuPDF4LLM-0288D1)](https://pymupdf.readthedocs.io/)
[![Infosys Springboard](https://img.shields.io/badge/Program-Infosys%20Springboard-007CC3)](https://infyspringboard.onwingspan.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Infosys Springboard Internship Project**  
> **Mentor:** Ankit Kumar Tripathy, Data Scientist  
> **Author:** Naman Bhatt  

An autonomous, multi-agent AI system designed to conduct systematic literature reviews and cross-paper syntheses. Powered by a stateful **LangGraph StateGraph** architecture, it automates the full pipeline from academic scoping and PDF retrieval to parallel draft generation and self-correcting peer-review loops.

---

## 📌 Table of Contents
- [Architecture & Workflow](#-architecture--workflow)
- [Milestone Delivery Checklist](#-milestone-delivery-checklist)
- [Key Features](#-key-features)
- [System Requirements & Tech Stack](#-system-requirements--tech-stack)
- [Quickstart & Installation](#-quickstart--installation)
- [Usage Modes](#-usage-modes)
  - [1. Autonomous CLI Execution](#1-autonomous-cli-execution)
  - [2. Interactive Modern Web Dashboard](#2-interactive-modern-web-dashboard)
  - [3. Graph Visualization & Export](#3-graph-visualization--export)
- [Project Structure](#-project-structure)
- [Quality Scoring & Peer-Review Heuristics](#-quality-scoring--peer-review-heuristics)
- [Internship Certificate](#-internship-certificate-of-completion)
- [License & Acknowledgments](#-license--acknowledgments)

---

## 🏗 Architecture & Workflow

The system is governed by a cyclic directed graph architecture using **LangGraph**:

```mermaid
graph TD;
    __start__([__start__]) --> process_input
    process_input --> planner
    planner --> researcher
    researcher --> search_articles
    search_articles --> article_decisions
    article_decisions --> download_articles
    download_articles --> paper_analyzer
    
    %% Parallel Fan-Out
    paper_analyzer --> write_abstract
    paper_analyzer --> write_conclusion
    paper_analyzer --> write_introduction
    paper_analyzer --> write_methods
    paper_analyzer --> write_references
    paper_analyzer --> write_results
    
    %% Aggregation
    write_abstract --> aggregate_paper
    write_conclusion --> aggregate_paper
    write_introduction --> aggregate_paper
    write_methods --> aggregate_paper
    write_references --> aggregate_paper
    write_results --> aggregate_paper
    
    aggregate_paper --> critique_paper
    
    %% Conditional Feedback Loops
    critique_paper -.->|Research Gaps Detected| search_articles
    critique_paper -.->|Score < 7.0| revise_paper
    critique_paper -.->|Quality Approved| final_draft
    
    revise_paper --> critique_paper
    final_draft --> __end__([__end__])
```

![Architecture Graph](docs/architecture_graph.png)

### StateGraph Nodes Breakdown
1. **`process_input`**: Normalizes topic slug, initializes persistent state tracking in SQLite, and validates parameters.
2. **`planner`**: Evaluates research scope, formulates core research questions, and derives optimized search queries.
3. **`researcher`**: Chooses primary queries or targeted secondary queries when triggered by gap detection.
4. **`search_articles`**: Queries the **Semantic Scholar API** (with automated **arXiv** fallback) for relevant open-access papers.
5. **`article_decisions`**: Evaluates candidates based on PDF availability, recency, and abstract richness (configurable limit, default: 3).
6. **`download_articles`**: Downloads open-access PDFs and validates document integrity.
7. **`paper_analyzer`**: Extracts structured markdown via `PyMuPDF4LLM` and isolates problem statements, methodologies, empirical discoveries, and novelty.
8. **Parallel Section Drafters**:
   - `write_abstract`: Generates an impactful abstract constrained strictly to **<= 100 words**.
   - `write_introduction`: Introduces the problem landscape, core concepts, and questions.
   - `write_methods`: Synthesizes experimental protocols and compares algorithms across papers.
   - `write_results`: Consolidates concrete discoveries, metrics, and empirical findings.
   - `write_conclusion`: Synthesizes final takeaways, practical implications, and future directions.
   - `write_references`: Generates deterministic **APA 7th-edition** bibliography and citation mappings.
9. **`aggregate_paper`**: Joins all 6 drafted sections into a unified `draft.md`.
10. **`critique_paper`**: Multi-dimensional quality evaluation (0–10) checking clarity, academic rigor, completeness, and citation usage. Also detects cross-paper knowledge gaps.
11. **`revise_paper`**: Rewrites weak sections incorporating specific actionable feedback, then loops back to `critique_paper`.
12. **`final_draft`**: Packages the publication-ready paper and compiles a standalone HTML report.

---

## 🏆 Milestone Delivery Checklist

| Milestone | Target Weeks | Requirements | Status |
| :--- | :---: | :--- | :---: |
| **Milestone 1** | Week 1–2 | • Setup environment & dependencies.<br>• Automated search via Semantic Scholar API & arXiv.<br>• Automatic PDF selection and download.<br>• Metadata dataset preparation (`papers.json`). | ✅ Complete |
| **Milestone 2** | Week 3–4 | • PyMuPDF4LLM section-wise parsing.<br>• Structured text extraction to Markdown.<br>• Key finding extraction (problems, methods, results, novelty).<br>• Cross-paper comparison matrix (`comparison.md`). | ✅ Complete |
| **Milestone 3** | Week 5–6 | • Parallel GPT-based section drafting.<br>• Strict 100-word limit enforcement on Abstract.<br>• Comparative Methods and Results synthesis.<br>• Deterministic APA 7th-edition reference formatting. | ✅ Complete |
| **Milestone 4** | Week 7–8 | • AI Peer-Review quality evaluation (0–10 scores).<br>• Automated revision loopback (`revise_paper` & gap re-search).<br>• **Gradio UI** with interactive 'Critique / Revise' controls.<br>• Modern interactive Web Dashboard (Flask/HTML5).<br>• Final compilation of standalone report. | ✅ Complete |

---

## ⚡ Key Features

- **Stateful LangGraph Orchestration**: Built with cyclic execution, fan-out parallel drafting, and intelligent self-reflection.
- **Direct Paper Link & PDF Support (Web/PDF)**: Feed any academic paper link (e.g. arXiv abstract, Nature, ScienceDirect, OpenReview, or direct `.pdf` link). The system automatically resolves metadata, retrieves the PDF, and initiates deep section drafting without manual searches.
- **Smart Dual Retrieval**: Semantic Scholar as primary open-access provider with automatic fallback to arXiv.
- **Rich Document Extraction**: Converts multi-column academic PDFs to clean Markdown using `PyMuPDF4LLM`.
- **Parallel Fan-out Section Drafting**: Synthesizes Abstract, Introduction, Methods, Results, Conclusion, and APA References simultaneously.
- **Iterative Reflection & AI Peer Review**: Evaluates prose quality with automated scoring (0–10) across clarity, rigor, and citation density.
- **Dual UI Flexibility**:
  - **Modern Web Dashboard**: Glassmorphic UI with pipeline status, interactive paper picker, and real-time history.
  - **Milestone 4 Gradio App**: Native Gradio interface with dedicated tabs and live "Critique / Revise" buttons.

---

## 💻 System Requirements & Tech Stack

- **Language:** Python 3.10+
- **Orchestration:** `langgraph`, `langchain-core`
- **PDF Extraction:** `pymupdf4llm`
- **LLM Engine:** OpenAI API / OpenRouter (`gpt-4o-mini`, `gpt-4o`, etc.)
- **User Interface:** Full-Stack Modern Web Application (`flask`, vanilla CSS/JS)
- **State & Storage:** SQLite (`data/state.db`) + local file artifacts

---

## 🚀 Quickstart & Installation

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/ai-research-reviewer.git
cd ai-research-reviewer
```

### 2. Set up virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your API credentials:
```env
OPENAI_API_KEY=your_openai_or_openrouter_key_here
OPENAI_BASE_URL=https://api.openai.com/v1   # or https://openrouter.ai/api/v1
APP_API_KEY=research_secret_123
```

---

## 🎮 Usage Modes

### 1. Autonomous CLI Execution
Execute the entire LangGraph workflow directly from your terminal:

**A. By Topic Search:**
```bash
python main.py run "Quantum Key Distribution in Satellite Networks" --limit 3
```

**B. By Direct Paper Link (Web or PDF URL):**
```bash
# Review an arXiv paper directly
python main.py run "https://arxiv.org/abs/1706.03762"

# Review a direct PDF link
python main.py run "https://arxiv.org/pdf/1706.03762.pdf"

# Review multiple papers via --url flag
python main.py run --url "https://arxiv.org/abs/1706.03762,https://arxiv.org/abs/2303.08774"
```

### 2. Interactive Modern Web Dashboard
Launch the polished web dashboard:
```bash
python main.py ui --port 5001
```
Open `http://localhost:5001` in your browser. Enter `APP_API_KEY` (configured in `.env`) to access:
- Live paper search and interactive paper screening.
- Real-time pipeline execution progress timeline.
- Embedded literature review reader with KaTeX formulas, section refinement, and publication exports.

### 3. Graph Visualization & Export
Display the architecture diagram and export it to PNG/Mermaid:
```bash
python main.py graph --export docs/architecture_graph.png
```

---

## 📂 Project Structure

```
.
├── main.py                     # Unified CLI & entry point
├── requirements.txt            # Dependency specifications
├── README.md                   # Project documentation
├── .env.example                # Environment template
│
├── src/
│   ├── graph/                  # LangGraph StateGraph engine
│   │   ├── state.py            # TypedDict ResearchState schema
│   │   ├── nodes.py            # 16 Graph nodes implementation
│   │   └── workflow.py         # Graph compilation, edges & routing
│   │
│   ├── core/                   # Core research engines
│   │   ├── planner.py          # Scoping and strategy formulation
│   │   ├── retrieval.py        # Semantic Scholar & arXiv client
│   │   ├── extraction.py       # PyMuPDF4LLM PDF parser
│   │   ├── analysis.py         # Finding extraction & gap detection
│   │   ├── drafting.py         # 6-section academic drafting
│   │   ├── references.py       # APA 7th bibliography generator
│   │   └── reviewer.py         # AI peer-review & heuristic scoring
│   │
│   ├── api/                    # Web Application & REST API
│   │   ├── app.py              # Flask server & background runners
│   │   ├── security.py         # Auth & rate-limiting middleware
│   │   └── templates/
│   │       └── dashboard.html  # Glassmorphic SaaS dashboard
│   │
│   ├── reports/
│   │   └── report_generator.py # Standalone HTML report generator
│   │
│   ├── data/
│   │   └── state_manager.py    # SQLite state & artifact ledger
│   │
│   └── utils/
│       └── logger.py           # Structured logger
│
├── data/                       # Local research artifact store (git-ignored)
│   ├── raw_pdfs/               # Downloaded research PDFs
│   ├── processed_text/         # Extracted markdown documents
│   ├── analysis/               # JSON findings & comparison matrix
│   ├── metadata/               # strategy.json & papers.json
│   └── drafts/                 # draft.md, refined_draft.md, report.html
│
└── docs/
    ├── architecture_graph.png  # Rendered LangGraph state diagram
    └── architecture_graph.mermaid
```

---

## 📊 Quality Scoring & Peer-Review Heuristics

The `DraftReviewer` module evaluates each generated draft across four dimensions:
1. **Clarity**: Analyzes sentence length variance, readability, and readability penalties for overly dense prose.
2. **Academic Rigor**: Evaluates critical thinking keywords (`contrast`, `limitation`, `bottleneck`, `tension`).
3. **Completeness**: Checks section-specific word budgets (including the **<= 100-word** constraint on the Abstract).
4. **Citation Usage**: Regex-based verification of `(Author, Year)` and `(Author et al., Year)` in-text citations.

If any section scores below the threshold (`REVIEW_PASSING_SCORE = 7`), the system triggers an automatic rewrite prompt with precise feedback.

---

## 🎓 Internship Certificate of Completion

> **Infosys Springboard Internship 6.0 (Batch 13)**  
> **Project:** *AI System to Review and Summarize Research Papers*  
> **Conducted:** *February 5, 2026 – April 3, 2026*  
> **Verification Portal:** [verify.onwingspan.com](https://verify.onwingspan.com)

<p align="center">
  <img src="docs/certificate_of_completion.png" alt="Infosys Springboard Certificate of Completion - Naman Bhatt" width="800"/>
</p>

---

## 📜 License & Acknowledgments

This project is licensed under the [MIT License](LICENSE).

Developed as part of the **Infosys Springboard Internship Program**. Special thanks to mentor **Ankit Kumar Tripathy** for architecture guidance and mentorship throughout the project.
