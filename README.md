# Automated Academic Research Paper Reviewer

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-FF4F00?logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![PyMuPDF](https://img.shields.io/badge/PDF_Parser-PyMuPDF4LLM-0288D1)](https://pymupdf.readthedocs.io/)
[![Infosys Springboard](https://img.shields.io/badge/Program-Infosys%20Springboard-007CC3)](https://infyspringboard.onwingspan.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A structured pipeline for automated academic literature reviews and cross-paper synthesis. Built with a cyclic directed graph architecture using LangGraph, the system handles topic scoping, open-access paper retrieval, full-text PDF section parsing, parallel multi-section drafting, and heuristic evaluation loops.

Developed for the **Infosys Springboard Internship 6.0 (Batch 13)** under the mentorship of **Ankit Kumar Tripathy**.

---

## Table of Contents
- [System Architecture](#system-architecture)
- [Pipeline Workflow](#pipeline-workflow)
- [Core Features](#core-features)
- [Tech Stack](#tech-stack)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
- [Project Layout](#project-layout)
- [Internship Certificate](#internship-certificate)
- [License](#license)

---

## System Architecture

The pipeline is implemented as a state machine using **LangGraph StateGraph**. Execution flows from user input through parallel fan-out drafting nodes to an aggregation and revision review loop.

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

<p align="center">
  <img src="docs/architecture_graph.png" alt="StateGraph Architecture Diagram" width="800"/>
</p>

---

## Pipeline Workflow

1. **Scoping (`planner`)**: Breaks the research topic down into core sub-questions and builds keyword search sets.
2. **Retrieval (`search_articles`, `download_articles`)**: Queries Semantic Scholar with automatic arXiv fallback. Alternatively, direct paper links or PDF URLs can be provided directly.
3. **Document Extraction (`paper_analyzer`)**: Uses `PyMuPDF4LLM` to extract text from multi-column PDFs, isolating problem statements, methodologies, datasets, and benchmark results.
4. **Parallel Section Drafting (`write_*`)**: Generates each section independently:
   - **Abstract**: Concise summary strictly constrained to $\le 100$ words.
   - **Introduction**: Problem background, research questions, and scope.
   - **Methods**: Algorithm and experimental setup comparison across papers.
   - **Results**: Empirical metrics and quantitative findings.
   - **Synthesis**: Cross-study comparison and remaining research gaps.
   - **References**: Deterministic APA 7th edition bibliography with verified in-text citations.
5. **Quality Review & Revision (`critique_paper`, `revise_paper`)**: Evaluates drafts using rule-based heuristics across clarity, academic rigor, completeness, and citation density. Sections scoring under the passing threshold ($7.0/10$) are revised automatically before final compilation.

---

## Core Features

- **Direct Link & PDF Ingestion**: Ingests direct academic links (arXiv IDs, paper URLs, or direct `.pdf` endpoints) to review specific literature without manual search queries.
- **Multi-Source Retrieval**: Queries the Semantic Scholar graph API with fallback to arXiv open-access servers.
- **Parallel Section Synthesis**: Drafts independent paper sections concurrently to minimize end-to-end latency.
- **Deterministic APA Referencing**: Formats complete bibliographic entries and validates parenthetical citations against retrieved metadata.
- **Web Interface**: Clean single-page dashboard featuring interactive paper screening, real-time pipeline status, KaTeX equation formatting, inline section editing, and PDF/Markdown exports.
- **State Persistence**: Uses SQLite (`data/state.db`) to record run logs, artifact paths, and workflow state.

---

## Tech Stack

| Component | Technology |
| :--- | :--- |
| Orchestration | LangGraph, LangChain Core |
| PDF Extraction | PyMuPDF (fitz), PyMuPDF4LLM |
| LLM Providers | OpenAI API, Groq, OpenRouter |
| Backend & API | Python 3.11+, Flask |
| Frontend | HTML5, Vanilla JavaScript, CSS, KaTeX |
| Database | SQLite |
| Testing | Pytest |

---

## Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone & Environment Setup
```bash
git clone https://github.com/Namanbhatt-01/ai-research-reviewer.git
cd ai-research-reviewer

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file from the example:
```bash
cp .env.example .env
```

Set the required environment variables:
```env
OPENAI_API_KEY=your_llm_api_key
OPENAI_BASE_URL=https://api.openai.com/v1   # Or OpenRouter/Groq URL
APP_API_KEY=research_secret_123
```

---

## Usage Guide

### Running the Web Dashboard
```bash
python main.py ui --port 5001
```
Open `http://localhost:5001` and supply your `APP_API_KEY`. Allows paper screening, monitoring pipeline progress, and reading/exporting reviews.

### Running via Terminal
```bash
# Run pipeline on a topic
python main.py run "Quantum Key Distribution in Satellite Networks" --limit 3

# Run directly on an arXiv link or PDF
python main.py run "https://arxiv.org/abs/1706.03762"
```

### Export Architecture Diagram
```bash
python main.py graph --export docs/architecture_graph.png
```

### Running Test Suite
```bash
python -m pytest tests/
```

---

## Project Layout

```
├── main.py                     # CLI entry point (terminal orchestrator & web server)
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── LICENSE                     # MIT license
├── .env.example                # Environment configuration template
│
├── src/
│   ├── api/                    # Flask server, authentication, dashboard template
│   │   ├── app.py
│   │   ├── security.py
│   │   └── templates/dashboard.html
│   │
│   ├── core/                   # Pipeline processing modules
│   │   ├── planner.py          # Scoping and query generation
│   │   ├── retrieval.py        # Semantic Scholar & arXiv search/download
│   │   ├── extraction.py       # PDF section extraction via PyMuPDF
│   │   ├── analysis.py         # Multi-paper finding extraction & comparison
│   │   ├── drafting.py         # Section drafting engine
│   │   ├── references.py       # APA 7th bibliography generator
│   │   └── reviewer.py         # Heuristic scoring and section refinement
│   │
│   ├── graph/                  # LangGraph state machine definitions
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── workflow.py
│   │
│   ├── reports/                # Offline report compilation
│   │   └── report_generator.py
│   │
│   ├── data/                   # SQLite database manager
│   │   └── state_manager.py
│   │
│   └── utils/                  # Application logging
│       └── logger.py
│
├── tests/                      # Automated test suite
│   ├── test_api_and_ui.py
│   ├── test_drafting_and_references.py
│   ├── test_graph_workflow.py
│   ├── test_retrieval.py
│   └── test_reviewer.py
│
└── docs/                       # Architecture diagrams and assets
    ├── architecture_graph.png
    ├── architecture_graph.mermaid
    └── certificate_of_completion.png
```

---

## Internship Certificate

Completed as part of the **Infosys Springboard Internship 6.0 (Batch 13)** under mentor **Ankit Kumar Tripathy**.

- **Project:** AI System to Review and Summarize Research Papers
- **Duration:** February 5, 2026 – April 3, 2026
- **Verification Portal:** [verify.onwingspan.com](https://verify.onwingspan.com)

<p align="center">
  <img src="docs/certificate_of_completion.png" alt="Infosys Springboard Certificate of Completion - Naman Bhatt" width="750"/>
</p>

---

## License

This project is licensed under the [MIT License](LICENSE).
