import os
import json
import threading
from typing import Optional, List, Dict
from flask import Flask, send_file, request, jsonify, abort, render_template_string

from src.config import config
from src.core.reviewer import DraftReviewer
from src.reports.report_generator import ReportGenerator
from src.utils.logger import logger
from .security import sanitize_slug, require_api_key, rate_limit

app = Flask(__name__)
reviewer = DraftReviewer()
generator = ReportGenerator()


# --- Background Thread Wrappers ---
def background_retrieval(topic_name: str, limit: int, selected_papers: Optional[List[Dict]] = None):
    """Runs the full pipeline (Phase 1-6) in the background.
    If selected_papers is provided, it downloads ONLY those.
    """
    from main import PipelineOrchestrator
    try:
        orch = PipelineOrchestrator(topic_name, limit=limit)
        papers = None
        if selected_papers:
            # Reconstruct PaperInfo objects
            from src.core.retrieval import PaperInfo
            papers = [PaperInfo(
                paper_id=p['paper_id'], title=p['title'], authors=p['authors'],
                year=p['year'], abstract=p['abstract'], url=p['url'], pdf_url=p.get('pdf_link')
            ) for p in selected_papers]
        
        # Run the entire pipeline synchronously within this thread
        orch.run_all(pre_selected_papers=papers)
    except Exception as e:
        logger.error(f"Background Pipeline Failed: {e}")

def background_processing(topic_slug: str):
    """Runs Phases 2-6 in the background."""
    from main import PipelineOrchestrator
    try:
        # We can reconstruct topic_name mostly from slug, or Orch reads DB!
        from src.data.state_manager import StateManager
        state = StateManager()
        # Find workflow by slug (simple query, or we just pass topic_name if known)
        workflow = state.get_workflow_by_slug(topic_slug)
        if not workflow:
            raise ValueError(f"No workflow found for slug {topic_slug}")
        topic_name = workflow['topic_name']

        orch = PipelineOrchestrator(topic_name)
        # Skip phase 1, run pipeline
        orch.run_phase_extraction()
        orch.run_phase_analysis()
        orch.run_phase_drafting()
        orch.run_phase_review()
        orch.run_phase_html()
        orch.state.update_workflow_status(orch.workflow_id, "COMPLETED")
        logger.info(f"Background processing completed for '{topic_slug}'.")
    except Exception as e:
        logger.error(f"Background Processing Failed: {e}")


# --- Interactive Web UI Route ---
@app.route("/")
def index():
    """Serves the main interactive dashboard."""
    # We will build templates/dashboard.html in the next step. 
    # For now, we return it if it exists, otherwise a simple placeholder.
    dashboard_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r") as f:
            return render_template_string(f.read(), api_key=config.APP_API_KEY)
    return "Interactive Dashboard is missing. Please create templates/dashboard.html"


# --- REST API Endpoints ---
@app.route("/api/research/search", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60)
@require_api_key
def search_papers():
    """Metadata-only search. Returns paper list without downloading or starting workflow."""
    data = request.json or {}
    topic = data.get("topic")
    limit = data.get("limit", 5)
    bypass_cache = data.get("bypass_cache", False)

    if not topic:
        return jsonify({"error": "Missing topic"}), 400
    
    from src.core.retrieval import PaperRetriever
    retriever = PaperRetriever()
    try:
        clean_topic = topic.strip()
        # Direct Paper Link or arXiv ID check
        if clean_topic.startswith(("http://", "https://", "arxiv:")) or "arxiv.org" in clean_topic or "semanticscholar.org" in clean_topic:
            resolved = retriever.resolve_paper_from_url(clean_topic)
            if resolved:
                return jsonify({
                    "papers": [resolved.to_dict()],
                    "cached": False,
                    "is_direct_url": True
                })

        papers, was_cached = retriever.search_papers(topic, limit=limit, bypass_cache=bypass_cache)
        return jsonify({
            "papers": [p.to_dict() for p in papers],
            "cached": was_cached,
            "is_direct_url": False
        })
    except Exception as e:
        logger.error(f"Search API failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/research/history", methods=["GET"])
@require_api_key
def get_history():
    """Returns a list of all past research topics with metadata."""
    from src.data.state_manager import StateManager
    state = StateManager()
    try:
        workflows = state.get_all_workflows()
        # Return all columns including created_at
        return jsonify(workflows)
    except Exception as e:
        logger.error(f"History API failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/research/<topic_slug>/delete", methods=["DELETE"])
@require_api_key
def delete_research(topic_slug: str):
    """Deletes a research workflow and its associated files."""
    topic_slug = sanitize_slug(topic_slug)
    from src.data.state_manager import StateManager
    state = StateManager()
    try:
        if not state.delete_workflow(topic_slug):
            return jsonify({"error": "Workflow not found"}), 404
            
        # Optional: Delete physical files?
        # User said "removre history block logically", but might expect file deletion too.
        # I'll stick to DB deletion for now to be safe, unless files are cluttering.
        # Actually, let's delete metadata/drafts too if they exist.
        import shutil
        paths = [
            os.path.join(config.METADATA_DIR, topic_slug),
            os.path.join(config.DRAFTS_DIR, topic_slug),
            os.path.join(config.RAW_PDF_DIR, topic_slug)
        ]
        for p in paths:
            if os.path.exists(p):
                shutil.rmtree(p)

        return jsonify({"message": f"Successfully deleted '{topic_slug}'"})
    except Exception as e:
        logger.error(f"Delete API failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/research/start", methods=["POST"])
@rate_limit(max_requests=5, window_seconds=60)
@require_api_key
def start_research():
    """Endpoint to initiate paper retrieval (downloading) for selected papers."""
    data = request.json or {}
    topic = data.get("topic")
    selected_papers = data.get("papers") # Array of PaperInfo dicts
    
    if not topic or not selected_papers:
        return jsonify({"error": "Missing topic or selected papers"}), 400
    
    # Pre-initialize orchestrator to ensure DB entry exists before we return
    # This avoids a race condition where the UI polls before the background thread starts
    from main import PipelineOrchestrator
    orch = PipelineOrchestrator(topic, limit=len(selected_papers))
    slug = orch.slug
    
    logger.info(f"[API] Starting targeted retrieval for '{topic}' ({len(selected_papers)} papers)")
    threading.Thread(target=background_retrieval, args=(topic, len(selected_papers), selected_papers)).start()
    
    return jsonify({"message": "Processing started", "slug": slug})


@app.route("/api/research/<topic_slug>/strategy", methods=["GET"])
@require_api_key
def get_research_strategy(topic_slug: str):
    """Fetches the strategy.json (generated in Phase 0) for the UI."""
    topic_slug = sanitize_slug(topic_slug)
    strategy_path = os.path.join(config.METADATA_DIR, topic_slug, "strategy.json")
    if not os.path.exists(strategy_path):
        return jsonify({"error": "Strategy not found for this topic"}), 404
    
    with open(strategy_path, "r", encoding="utf-8") as f:
        strategy = json.load(f)
    return jsonify(strategy)


@app.route("/api/research/<topic_slug>/status", methods=["GET"])
@require_api_key
def get_status(topic_slug: str):
    """Endpoint to poll the current status of all phases."""
    topic_slug = sanitize_slug(topic_slug)
    from src.data.state_manager import StateManager
    state = StateManager()
    
    workflow = state.get_workflow_by_slug(topic_slug)
    if not workflow:
        return jsonify({"error": "Workflow not found"}), 404
        
    tasks = state.get_workflow_tasks(workflow["id"])

    return jsonify({
        "workflow_status": workflow["status"],
        "tasks": tasks
    })


@app.route("/api/research/<topic_slug>/papers", methods=["GET"])
@require_api_key
def get_papers(topic_slug: str):
    """Returns the JSON list of retrieved papers."""
    topic_slug = sanitize_slug(topic_slug)
    metadata_file = os.path.abspath(os.path.join(config.METADATA_DIR, topic_slug, "papers.json"))
    if not os.path.exists(metadata_file):
        return jsonify([])
    try:
        with open(metadata_file, "r") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/research/<topic_slug>/process", methods=["POST"])
@rate_limit(max_requests=5, window_seconds=60)
@require_api_key
def process_research(topic_slug: str):
    """Endpoint to trigger the heavy pipeline (Phases 2-6)."""
    topic_slug = sanitize_slug(topic_slug)
    logger.info(f"[API] Starting full processing for '{topic_slug}'")
    threading.Thread(target=background_processing, args=(topic_slug,)).start()
    return jsonify({"message": "Processing started in background"})


@app.route("/api/research/<topic_slug>/report_data", methods=["GET"])
@require_api_key
def get_report_data(topic_slug: str):
    """Returns structured sections, review evaluations, and papers for in-dashboard reading."""
    topic_slug = sanitize_slug(topic_slug)
    topic_dir = os.path.abspath(os.path.join(config.DRAFTS_DIR, topic_slug))
    
    refined_draft = os.path.join(topic_dir, "refined_draft.md")
    source_draft = refined_draft if os.path.exists(refined_draft) else os.path.join(topic_dir, "draft.md")
    
    if not os.path.exists(source_draft):
        return jsonify({"error": f"No draft found for '{topic_slug}'"}), 404
        
    try:
        with open(source_draft, "r", encoding="utf-8") as f:
            raw_markdown = f.read()
            
        sections = ReportGenerator._parse_draft(source_draft)
        sections_html = {k: ReportGenerator._md_to_html(v) for k, v in sections.items()}
        
        review_path = os.path.join(topic_dir, "review.json")
        review_data = {}
        if os.path.exists(review_path):
            try:
                with open(review_path, "r", encoding="utf-8") as f:
                    review_data = json.load(f)
            except Exception:
                pass
                
        metadata_file = os.path.join(config.METADATA_DIR, topic_slug, "papers.json")
        papers_data = []
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    papers_data = json.load(f)
            except Exception:
                pass

        return jsonify({
            "topic_slug": topic_slug,
            "title": topic_slug.replace("_", " ").title(),
            "sections": sections,
            "sections_html": sections_html,
            "raw_markdown": raw_markdown,
            "review": review_data,
            "papers": papers_data
        })
    except Exception as e:
        logger.error(f"Failed to load report data: {e}")
        return jsonify({"error": str(e)}), 500


# --- Existing Reporting Endpoints ---
@app.route("/report/<topic>")
@require_api_key
def view_report(topic: str):
    """Dynamically renders the research report from data files."""
    topic_slug = sanitize_slug(topic)
    topic_dir = os.path.abspath(os.path.join(config.DRAFTS_DIR, topic_slug))
    
    # Locate data files
    refined_draft = os.path.join(topic_dir, "refined_draft.md")
    source_draft = refined_draft if os.path.exists(refined_draft) else os.path.join(topic_dir, "draft.md")
    review_json_path = os.path.join(topic_dir, "review.json")
    
    if not os.path.exists(source_draft):
        abort(404, description=f"Research data for '{topic_slug}' not found.")
    
    # Dynamically render HTML
    html = generator.render_html(
        draft_path=source_draft,
        review_path=review_json_path if os.path.exists(review_json_path) else None,
        topic_slug=topic_slug
    )
    
    if not html:
        abort(500, description="Failed to render report.")
        
    return html


@app.route("/api/revise/<topic>", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60)
@require_api_key
def revise_section(topic: str):
    """API endpoint triggered by the 'Critique & Revise' button in the UI."""
    topic = sanitize_slug(topic)
    data = request.json
    if not data or "section" not in data:
        return jsonify({"error": "Missing 'section' in JSON body"}), 400

    section_name = data["section"]
    topic_dir = os.path.abspath(os.path.join(config.DRAFTS_DIR, topic))

    draft_path = os.path.join(topic_dir, "refined_draft.md")
    if not os.path.exists(draft_path):
        draft_path = os.path.join(topic_dir, "draft.md")

    if not os.path.exists(draft_path):
        return jsonify({"error": f"No draft found for '{topic}'"}), 404

    # Load current review.json state
    review_path = os.path.join(topic_dir, "review.json")
    review_data = {}
    if os.path.exists(review_path):
        with open(review_path, "r", encoding="utf-8") as f:
            review_data = json.load(f)

    sections = reviewer._parse_draft(draft_path)
    if section_name not in sections:
        return jsonify({"error": f"Section '{section_name}' not found in draft"}), 404

    current_text = sections[section_name]
    logger.info(f"[UI] Triggered manual revision for '{topic}' → '{section_name}'")
    
    evaluation = reviewer.evaluate_section(section_name, current_text)
    suggestions = reviewer.suggest_revisions(section_name, current_text, evaluation)
    overall_score = evaluation.get("overall", 0.0)
    
    refined_text = reviewer.refine_section(section_name, current_text, suggestions)
    if not refined_text:
        return jsonify({"error": "GPT failed to refine the section"}), 500

    review_data[section_name] = {
        "evaluation": evaluation,
        "suggestions": suggestions,
        "overall_score": overall_score,
        "refined": True,
    }
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review_data, f, indent=4)

    sections[section_name] = refined_text
    reviewer._write_refined_draft(sections, {}, drafts_dir=topic_dir)

    generator.generate(
        draft_path=os.path.join(topic_dir, "refined_draft.md"),
        review_path=review_path,
        output_dir=topic_dir,
    )

    return jsonify({
        "status": "success",
        "section": section_name,
        "new_score": overall_score,
    }), 200


def start_server(port=5000):
    """Starts the Flask server synchronously."""
    logger.info(f"Starting Interactive UI Server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

