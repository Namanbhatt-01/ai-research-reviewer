"""
Graph nodes implementation matching the exact state graph blueprint:
__start__ -> process_input -> planner -> researcher -> search_articles
-> article_decisions -> download_articles -> paper_analyzer
-> [write_abstract, write_conclusion, write_introduction, write_methods, write_references, write_results]
-> aggregate_paper -> critique_paper -> (search_articles | revise_paper | final_draft)
-> final_draft -> __end__
"""

import os
import re
import json
from typing import Dict, Any, List, Optional

from src.config import config
from src.utils.logger import logger
from src.graph.state import ResearchState
from src.core.retrieval import PaperRetriever, PaperInfo
from src.core.extraction import PDFExtractor
from src.core.analysis import PaperAnalyzer
from src.core.planner import ResearchPlanner
from src.core.drafting import SectionDrafter
from src.core.reviewer import DraftReviewer
from src.core.references import APAFormatter
from src.reports.report_generator import ReportGenerator
from src.data.state_manager import StateManager


def _topic_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    return slug[:60]


def _get_topic_dirs(slug: str) -> Dict[str, str]:
    dirs = {
        "pdf": os.path.join(config.RAW_PDF_DIR, slug),
        "text": os.path.join(config.PROCESSED_TEXT_DIR, slug),
        "analysis": os.path.join(config.ANALYSIS_DIR, slug),
        "metadata": os.path.join(config.METADATA_DIR, slug),
        "drafts": os.path.join(config.DRAFTS_DIR, slug),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


# ----------------------------------------------------------------------
# 1. process_input
# ----------------------------------------------------------------------
def process_input(state: ResearchState) -> Dict[str, Any]:
    topic = state.get("topic", "").strip()
    if not topic:
        topic = "Artificial Intelligence in Academic Research"
    slug = state.get("slug") or _topic_slug(topic)
    limit = state.get("limit") or config.ARXIV_LIMIT_DEFAULT

    # Ensure directories
    _get_topic_dirs(slug)

    # Initialize StateManager workflow
    sm = StateManager()
    workflow = sm.get_or_create_workflow(topic, slug)

    logger.info(f"[Node: process_input] Initialized workflow #{workflow['id']} for '{topic}' (slug: {slug})")
    return {
        "topic": topic,
        "slug": slug,
        "limit": limit,
        "workflow_id": workflow["id"],
        "revision_count": state.get("revision_count", 0),
        "max_revisions": state.get("max_revisions", 2),
        "search_cycle": state.get("search_cycle", 0),
        "max_search_cycles": state.get("max_search_cycles", 1),
        "needs_more_research": False,
        "needs_revision": False,
        "status": "PROCESSING",
        "current_step": "process_input",
    }


# ----------------------------------------------------------------------
# 2. planner
# ----------------------------------------------------------------------
def planner(state: ResearchState) -> Dict[str, Any]:
    topic = state["topic"]
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    logger.info(f"[Node: planner] Generating research plan for topic: '{topic}'")

    sm = StateManager()
    task_id = sm.create_or_start_task(state.get("workflow_id", 1), "planning")

    try:
        rp = ResearchPlanner()
        plan = rp.generate_plan(topic)
        if not plan:
            plan = {
                "refined_topic": topic,
                "optimized_queries": [topic, f"{topic} review", f"{topic} methodologies"],
                "key_questions": ["What is the foundational approach?", "What are the recent advancements?"],
                "structural_goal": f"A comprehensive systematic review of {topic}",
            }

        plan_path = os.path.join(dirs["metadata"], "strategy.json")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=4)

        sm.log_artifact(task_id, "research_strategy", plan_path)
        sm.mark_task_complete(task_id)

        queries = plan.get("optimized_queries", [topic])
        return {
            "plan": plan,
            "optimized_queries": queries,
            "current_step": "planner",
        }
    except Exception as e:
        logger.error(f"[Node: planner] Error: {e}")
        sm.mark_task_failed(task_id, str(e))
        return {
            "plan": {"refined_topic": topic, "optimized_queries": [topic]},
            "optimized_queries": [topic],
            "current_step": "planner",
        }


# ----------------------------------------------------------------------
# 3. researcher
# ----------------------------------------------------------------------
def researcher(state: ResearchState) -> Dict[str, Any]:
    logger.info("[Node: researcher] Determining targeted search query...")
    # If secondary query exists from a gap reflection cycle, prioritize it
    if state.get("secondary_query") and state.get("needs_more_research"):
        target_query = state["secondary_query"]
        logger.info(f"[Node: researcher] Using targeted gap-fill query: '{target_query}'")
    else:
        queries = state.get("optimized_queries", [])
        target_query = queries[0] if queries else state.get("topic", "")

    return {
        "research_query": target_query,
        "current_step": "researcher",
    }


# ----------------------------------------------------------------------
# 4. search_articles
# ----------------------------------------------------------------------
def search_articles(state: ResearchState) -> Dict[str, Any]:
    query = state.get("research_query") or state.get("topic")
    limit = state.get("limit", 3)
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    cycle = state.get("search_cycle", 0)

    logger.info(f"[Node: search_articles] Searching articles for '{query}' (limit={limit}, cycle={cycle})")

    sm = StateManager()
    task_id = sm.create_or_start_task(state.get("workflow_id", 1), f"retrieval_{cycle}")

    try:
        retriever = PaperRetriever()
        papers, _ = retriever.search_papers(query, limit=limit, bypass_cache=(cycle > 0))
        if not papers:
            logger.warning("[Node: search_articles] No papers returned from primary search, using fallback query.")
            papers = retriever.search_arxiv(query, limit=limit)

        papers_data = [p.to_dict() for p in papers]

        # Save metadata
        retriever.save_metadata(papers, folder=dirs["metadata"], append=(cycle > 0))
        sm.log_artifact(task_id, "papers_json", os.path.join(dirs["metadata"], "papers.json"))
        sm.mark_task_complete(task_id)

        # Merge with existing raw articles if cyclic search
        existing = state.get("raw_articles", [])
        combined = existing + papers_data
        # Deduplicate by paper_id or title
        seen = set()
        deduped = []
        for p in combined:
            pid = p.get("paper_id") or p.get("title")
            if pid not in seen:
                seen.add(pid)
                deduped.append(p)

        return {
            "raw_articles": deduped,
            "needs_more_research": False,
            "secondary_query": None,
            "current_step": "search_articles",
        }
    except Exception as e:
        logger.error(f"[Node: search_articles] Search error: {e}")
        sm.mark_task_failed(task_id, str(e))
        return {
            "raw_articles": state.get("raw_articles", []),
            "current_step": "search_articles",
        }


# ----------------------------------------------------------------------
# 5. article_decisions
# ----------------------------------------------------------------------
def article_decisions(state: ResearchState) -> Dict[str, Any]:
    articles = state.get("raw_articles", [])
    limit = state.get("limit", 3)
    logger.info(f"[Node: article_decisions] Filtering & picking top {limit} papers from {len(articles)} candidates.")

    # Prioritize papers with accessible PDFs and rich abstracts
    scored_articles = []
    for art in articles:
        score = 0
        if art.get("pdf_link"):
            score += 5
        if art.get("abstract") and len(art["abstract"]) > 100:
            score += 3
        if art.get("year"):
            score += 1
        scored_articles.append((score, art))

    scored_articles.sort(key=lambda x: x[0], reverse=True)
    selected = [art for _, art in scored_articles[:limit]]

    logger.info(f"[Node: article_decisions] Selected {len(selected)} papers.")
    return {
        "selected_articles": selected,
        "current_step": "article_decisions",
    }


# ----------------------------------------------------------------------
# 6. download_articles
# ----------------------------------------------------------------------
def download_articles(state: ResearchState) -> Dict[str, Any]:
    selected = state.get("selected_articles", [])
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    logger.info(f"[Node: download_articles] Downloading PDFs for {len(selected)} papers into {dirs['pdf']}")

    papers = [
        PaperInfo(
            paper_id=p.get("paper_id", ""),
            title=p.get("title", ""),
            authors=p.get("authors", []),
            year=str(p.get("year", "")),
            abstract=p.get("abstract", ""),
            url=p.get("url", ""),
            pdf_url=p.get("pdf_link"),
        )
        for p in selected
    ]

    retriever = PaperRetriever()
    downloaded_paths = retriever.download_papers(papers, dirs["pdf"])

    return {
        "downloaded_pdfs": downloaded_paths,
        "current_step": "download_articles",
    }


# ----------------------------------------------------------------------
# 7. paper_analyzer
# ----------------------------------------------------------------------
def paper_analyzer(state: ResearchState) -> Dict[str, Any]:
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    logger.info("[Node: paper_analyzer] Extracting Markdown text and analyzing key findings...")

    sm = StateManager()
    cycle = state.get("search_cycle", 0)
    task_id = sm.create_or_start_task(state.get("workflow_id", 1), f"analysis_{cycle}")

    try:
        # Step 1: Text extraction with PyMuPDF4LLM
        extractor = PDFExtractor()
        extracted_paths = extractor.process_directory(dirs["pdf"], dirs["text"])
        logger.info(f"[Node: paper_analyzer] Extracted {len(extracted_paths)} markdown documents.")

        # Step 2: Findings extraction
        analyzer = PaperAnalyzer()
        text_files = [os.path.join(dirs["text"], f) for f in os.listdir(dirs["text"]) if f.endswith(".md")]
        findings = analyzer.analyze_papers(file_paths=text_files, analysis_dir=dirs["analysis"])
        comparison = analyzer.compare_papers(findings, analysis_dir=dirs["analysis"])

        sm.log_artifact(task_id, "analysis_json", os.path.join(dirs["analysis"], "key_findings.json"))
        sm.mark_task_complete(task_id)

        return {
            "findings": findings,
            "comparison": comparison,
            "current_step": "paper_analyzer",
        }
    except Exception as e:
        logger.error(f"[Node: paper_analyzer] Analysis failed: {e}")
        sm.mark_task_failed(task_id, str(e))
        return {
            "findings": {},
            "comparison": "",
            "current_step": "paper_analyzer",
        }


# ----------------------------------------------------------------------
# 8. Parallel Writing Nodes
# ----------------------------------------------------------------------
def write_abstract(state: ResearchState) -> Dict[str, Any]:
    findings = state.get("findings", {})
    logger.info("[Node: write_abstract] Drafting Abstract (100-word limit)...")
    drafter = SectionDrafter()
    abstract = drafter.draft_abstract(findings) or "Abstract generation failed."
    return {"abstract": abstract}


def write_introduction(state: ResearchState) -> Dict[str, Any]:
    findings = state.get("findings", {})
    plan = state.get("plan", {})
    logger.info("[Node: write_introduction] Drafting Introduction...")
    drafter = SectionDrafter()
    intro = drafter.draft_introduction(findings, plan) or "Introduction generation failed."
    return {"introduction": intro}


def write_methods(state: ResearchState) -> Dict[str, Any]:
    findings = state.get("findings", {})
    logger.info("[Node: write_methods] Drafting Methods comparison...")
    drafter = SectionDrafter()
    methods = drafter.draft_methods(findings) or "Methods generation failed."
    return {"methods": methods}


def write_results(state: ResearchState) -> Dict[str, Any]:
    findings = state.get("findings", {})
    logger.info("[Node: write_results] Drafting Results synthesis...")
    drafter = SectionDrafter()
    results = drafter.draft_results(findings) or "Results generation failed."
    return {"results": results}


def write_conclusion(state: ResearchState) -> Dict[str, Any]:
    findings = state.get("findings", {})
    logger.info("[Node: write_conclusion] Drafting Conclusion & future outlook...")
    drafter = SectionDrafter()
    conclusion = drafter.draft_conclusion(findings) or "Conclusion generation failed."
    return {"conclusion": conclusion}


def write_references(state: ResearchState) -> Dict[str, Any]:
    logger.info("[Node: write_references] Formatting APA 7th-edition references...")
    articles = state.get("selected_articles", [])
    papers = [
        PaperInfo(
            paper_id=p.get("paper_id", ""),
            title=p.get("title", ""),
            authors=p.get("authors", []),
            year=str(p.get("year", "")),
            abstract=p.get("abstract", ""),
            url=p.get("url", ""),
            pdf_url=p.get("pdf_link"),
        )
        for p in articles
    ]
    formatter = APAFormatter()
    ref_block = formatter.format_reference_list(papers)
    return {"references": ref_block}


# ----------------------------------------------------------------------
# 9. aggregate_paper
# ----------------------------------------------------------------------
def aggregate_paper(state: ResearchState) -> Dict[str, Any]:
    topic = state.get("topic", "Research Synthesis")
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    logger.info("[Node: aggregate_paper] Combining parallel drafted sections into unified draft.md...")

    abstract = state.get("abstract", "_Abstract pending._")
    intro = state.get("introduction", "_Introduction pending._")
    methods = state.get("methods", "_Methods pending._")
    results = state.get("results", "_Results pending._")
    conclusion = state.get("conclusion", "_Conclusion pending._")
    references = state.get("references", "_References pending._")

    lines = [
        f"# Systematic Literature Review: {topic}\n",
        "## Abstract\n",
        abstract + "\n",
        "## Introduction\n",
        intro + "\n",
        "## Methods\n",
        methods + "\n",
        "## Results\n",
        results + "\n",
        "## Conclusion\n",
        conclusion + "\n",
        "## References\n",
        references + "\n",
    ]

    draft_text = "\n".join(lines)
    draft_path = os.path.join(dirs["drafts"], "draft.md")
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(draft_text)

    sm = StateManager()
    task_id = sm.create_or_start_task(state.get("workflow_id", 1), "drafting")
    sm.log_artifact(task_id, "draft_md", draft_path)
    sm.mark_task_complete(task_id)

    return {
        "aggregated_draft": draft_text,
        "draft_path": draft_path,
        "current_step": "aggregate_paper",
    }


# ----------------------------------------------------------------------
# 10. critique_paper
# ----------------------------------------------------------------------
def critique_paper(state: ResearchState) -> Dict[str, Any]:
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    draft_path = state.get("draft_path") or os.path.join(dirs["drafts"], "draft.md")
    logger.info(f"[Node: critique_paper] Evaluating draft quality and checking research gaps...")

    sm = StateManager()
    task_id = sm.create_or_start_task(state.get("workflow_id", 1), "review")

    reviewer = DraftReviewer()
    review_summary = reviewer.review_draft(draft_path, drafts_dir=dirs["drafts"])
    review_path = os.path.join(dirs["drafts"], "review.json")

    # Check for research gaps to see if additional search cycle is needed
    plan = state.get("plan", {})
    findings = state.get("findings", {})
    analyzer = PaperAnalyzer()
    gaps = analyzer.identify_gaps(plan, findings, analysis_dir=dirs["analysis"])

    search_cycle = state.get("search_cycle", 0)
    max_search_cycles = state.get("max_search_cycles", 1)
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    needs_more_research = False
    secondary_query = None

    if gaps and gaps.get("has_gaps") and search_cycle < max_search_cycles:
        needs_more_research = True
        secondary_query = gaps.get("secondary_query")
        search_cycle += 1
        logger.info(f"[Node: critique_paper] Knowledge gap detected! Triggering research cycle {search_cycle} with: '{secondary_query}'")

    needs_revision = False
    if not needs_more_research and review_summary:
        overall_score = review_summary.get("overall_score", 10.0)
        sections = review_summary.get("sections", {})
        has_low_score = any(s.get("overall", 10) < config.REVIEW_PASSING_SCORE for s in sections.values())
        if (overall_score < config.REVIEW_PASSING_SCORE or has_low_score) and revision_count < max_revisions:
            needs_revision = True
            logger.info(f"[Node: critique_paper] Score ({overall_score}) < passing threshold. Triggering revision cycle {revision_count + 1}.")

    sm.log_artifact(task_id, "review_json", review_path)
    sm.mark_task_complete(task_id)

    return {
        "review": review_summary,
        "review_path": review_path,
        "needs_more_research": needs_more_research,
        "secondary_query": secondary_query,
        "search_cycle": search_cycle,
        "needs_revision": needs_revision,
        "current_step": "critique_paper",
    }


# ----------------------------------------------------------------------
# 11. revise_paper
# ----------------------------------------------------------------------
def revise_paper(state: ResearchState) -> Dict[str, Any]:
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    draft_path = state.get("draft_path") or os.path.join(dirs["drafts"], "draft.md")
    count = state.get("revision_count", 0) + 1
    logger.info(f"[Node: revise_paper] Executing revision cycle #{count}...")

    reviewer = DraftReviewer()
    # Review draft also writes refined_draft.md if needed
    review_summary = reviewer.review_draft(draft_path, drafts_dir=dirs["drafts"])
    refined_path = os.path.join(dirs["drafts"], "refined_draft.md")

    refined_content = state.get("aggregated_draft", "")
    if os.path.exists(refined_path):
        with open(refined_path, "r", encoding="utf-8") as f:
            refined_content = f.read()

    return {
        "aggregated_draft": refined_content,
        "draft_path": refined_path,
        "revision_count": count,
        "needs_revision": False,
        "current_step": "revise_paper",
    }


# ----------------------------------------------------------------------
# 12. final_draft
# ----------------------------------------------------------------------
def final_draft(state: ResearchState) -> Dict[str, Any]:
    slug = state["slug"]
    dirs = _get_topic_dirs(slug)
    logger.info("[Node: final_draft] Finalizing publication-ready draft and generating HTML report...")

    refined_draft = os.path.join(dirs["drafts"], "refined_draft.md")
    draft_path = refined_draft if os.path.exists(refined_draft) else os.path.join(dirs["drafts"], "draft.md")

    with open(draft_path, "r", encoding="utf-8") as f:
        final_content = f.read()

    # Generate polished HTML report
    generator = ReportGenerator()
    review_path = os.path.join(dirs["drafts"], "review.json")
    html_path = generator.generate(
        draft_path=draft_path,
        review_path=review_path if os.path.exists(review_path) else None,
        output_dir=dirs["drafts"],
    )

    sm = StateManager()
    workflow_id = state.get("workflow_id", 1)
    task_id = sm.create_or_start_task(workflow_id, "html")
    sm.log_artifact(task_id, "html_report", html_path)
    sm.mark_task_complete(task_id)
    sm.update_workflow_status(workflow_id, "COMPLETED")

    logger.info(f"[Node: final_draft] Workflow completed successfully! HTML: {html_path}")
    return {
        "final_draft": final_content,
        "final_draft_path": draft_path,
        "html_report_path": html_path,
        "status": "COMPLETED",
        "current_step": "final_draft",
    }
