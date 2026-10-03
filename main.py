import os
import argparse
import re
import json
from typing import List, Optional, Any, Tuple, Dict

from src.config import config
from src.utils.logger import logger
from src.core.retrieval import PaperRetriever, PaperInfo
from src.core.extraction import PDFExtractor
from src.core.analysis import PaperAnalyzer
from src.core.planner import ResearchPlanner
from src.core.drafting import SectionDrafter
from src.core.reviewer import DraftReviewer
from src.reports.report_generator import ReportGenerator
from src.api.app import start_server
from src.data.state_manager import StateManager


def _topic_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    return slug[:60]


class PipelineOrchestrator:
    def __init__(self, topic_name: str, limit: int = config.ARXIV_LIMIT_DEFAULT):
        self.topic_name = topic_name.strip()
        self.slug = _topic_slug(self.topic_name)
        self.limit = limit
        self.state = StateManager()
        self.loop_count = 0
        self.max_loops = 1  # Limit recursive research to 1 extra cycle for now
        
        # Initialize workflow
        self.workflow = self.state.get_or_create_workflow(self.topic_name, self.slug)
        self.workflow_id = self.workflow['id']
        logger.info(f"Initialized Workflow #{self.workflow_id} for topic: '{self.topic_name}'")

        self.topic_pdf_dir       = os.path.join(config.RAW_PDF_DIR,        self.slug)
        self.topic_text_dir      = os.path.join(config.PROCESSED_TEXT_DIR, self.slug)
        self.topic_analysis_dir  = os.path.join(config.ANALYSIS_DIR,       self.slug)
        self.topic_metadata_dir  = os.path.join(config.METADATA_DIR,       self.slug)
        self.topic_drafts_dir    = os.path.join(config.DRAFTS_DIR,         self.slug)

        for d in (self.topic_pdf_dir, self.topic_text_dir, self.topic_analysis_dir, self.topic_metadata_dir, self.topic_drafts_dir):
            os.makedirs(d, exist_ok=True)

    def _should_run_phase(self, phase_name: str) -> bool:
        task = self.state.get_task(self.workflow_id, phase_name)
        if task and task['status'] == 'COMPLETED':
            logger.info(f"Phase '{phase_name}' already completed. Skipping.")
            return False
        return True

    def run_phase_planning(self) -> bool:
        if not self._should_run_phase("planning"): return True
        task_id = self.state.create_or_start_task(self.workflow_id, "planning")
        try:
            logger.info("--- Phase 0: Research Planning ---")
            planner = ResearchPlanner()
            plan = planner.generate_plan(self.topic_name)
            if not plan:
                raise Exception("Failed to generate research strategy.")
            
            plan_path = os.path.join(self.topic_metadata_dir, "strategy.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=4)
            
            self.state.log_artifact(task_id, "research_strategy", plan_path)
            self.state.mark_task_complete(task_id)
            return True
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False

    def run_phase_retrieval(self, pre_selected_papers: Optional[List[PaperInfo]] = None, query_override: Optional[str] = None) -> bool:
        """
        Phase 1: Search and Download PDFs.
        """
        if not self._should_run_phase(f"retrieval_{self.loop_count}"): return True
        task_id = self.state.create_or_start_task(self.workflow_id, f"retrieval_{self.loop_count}")
        try:
            logger.info(f"--- Phase 1: Retrieval (Cycle {self.loop_count}) ---")
            retriever = PaperRetriever()
            
            if query_override:
                logger.info(f"Performing targeted secondary search: {query_override}")
                papers = retriever.search_arxiv(query_override, limit=5)
            elif pre_selected_papers:
                papers = pre_selected_papers
            else:
                papers = retriever.search_arxiv(self.topic_name, limit=self.limit)

            if not papers:
                raise Exception("No papers found for the topic.")

            # Save metadata so other phases can find it
            retriever.save_metadata(papers, folder=self.topic_metadata_dir, append=(self.loop_count > 0))

            downloaded_paths = retriever.download_papers(papers, self.topic_pdf_dir)
            
            if not downloaded_paths:
                raise Exception("Failed to download any PDFs.")

            self.state.log_artifact(task_id, "papers_json", os.path.join(self.topic_metadata_dir, "papers.json"))
            self.state.mark_task_complete(task_id)
            return True
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False

    def run_phase_extraction(self) -> bool:
        task_name = f"extraction_{self.loop_count}"
        if not self._should_run_phase(task_name): return True
        task_id = self.state.create_or_start_task(self.workflow_id, task_name)
        try:
            logger.info("--- Phase 2: Text Extraction ---")
            extractor = PDFExtractor()
            extracted_paths = extractor.process_directory(self.topic_pdf_dir, self.topic_text_dir)
            if not extracted_paths:
                raise Exception("No text files were extracted.")
            
            for path in extracted_paths:
                self.state.log_artifact(task_id, "processed_text", path)
                
            self.state.mark_task_complete(task_id)
            return True
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False

    def run_phase_analysis(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        task_name = f"analysis_{self.loop_count}"
        if not self._should_run_phase(task_name): return True
        task_id = self.state.create_or_start_task(self.workflow_id, task_name)
        try:
            logger.info("--- Phase 3: Analysis ---")
            analyzer = PaperAnalyzer()
            
            extracted_paths = [os.path.join(self.topic_text_dir, f) for f in os.listdir(self.topic_text_dir) if f.endswith('.md')]
            
            findings = analyzer.analyze_papers(file_paths=extracted_paths, analysis_dir=self.topic_analysis_dir)
            if not findings:
                raise Exception("No findings extracted.")
            self.state.log_artifact(task_id, "analysis_json", os.path.join(self.topic_analysis_dir, "key_findings.json"))
            
            comparison = analyzer.compare_papers(findings, analysis_dir=self.topic_analysis_dir)
            if comparison:
                self.state.log_artifact(task_id, "comparison_md", os.path.join(self.topic_analysis_dir, "comparison.md"))
            
            self.state.mark_task_complete(task_id)
            
            # --- Advanced Agentic: Identify Gaps ---
            strategy_path = os.path.join(self.topic_metadata_dir, "strategy.json")
            if os.path.exists(strategy_path):
                with open(strategy_path, "r", encoding="utf-8") as f:
                    strategy = json.load(f)
                gaps = analyzer.identify_gaps(strategy, findings, analysis_dir=self.topic_analysis_dir)
                if gaps and gaps.get("has_gaps"):
                    logger.info(f"Knowledge Gaps Found! Secondary Query: {gaps.get('secondary_query')}")
                    return True, gaps # Return gaps info to trigger loop
            
            return True, None
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False, None

    def run_phase_drafting(self) -> bool:
        if not self._should_run_phase("drafting"): return True
        task_id = self.state.create_or_start_task(self.workflow_id, "drafting")
        try:
            logger.info("--- Phase 4: Drafting ---")
            drafter = SectionDrafter()
            
            findings_path = os.path.join(self.topic_analysis_dir, "key_findings.json")
            with open(findings_path, "r") as f:
                findings = json.load(f)
            
            paper_json = os.path.join(self.topic_metadata_dir, "papers.json")
            with open(paper_json, "r") as f:
                p_data = json.load(f)
                
            papers = [PaperInfo(
                paper_id=p['paper_id'], title=p['title'], authors=p['authors'],
                year=p['year'], abstract=p['abstract'], url=p['url'], pdf_url=p.get('pdf_link')
            ) for p in p_data]
            
            draft_path = drafter.draft_all(findings, drafts_dir=self.topic_drafts_dir, papers=papers)
            if not draft_path:
                raise Exception("Draft generation failed.")
                
            self.state.log_artifact(task_id, "draft_md", draft_path)
            self.state.mark_task_complete(task_id)
            return True
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False

    def run_phase_review(self) -> bool:
        if not self._should_run_phase("review"): return True
        task_id = self.state.create_or_start_task(self.workflow_id, "review")
        try:
            logger.info("--- Phase 5: Review & Refinement ---")
            reviewer = DraftReviewer()
            draft_path = os.path.join(self.topic_drafts_dir, "draft.md")
            review_summary = reviewer.review_draft(draft_path, drafts_dir=self.topic_drafts_dir)
            if review_summary:
                self.state.log_artifact(task_id, "review_json", os.path.join(self.topic_drafts_dir, "review.json"))
                self.state.log_artifact(task_id, "refined_draft_md", os.path.join(self.topic_drafts_dir, "refined_draft.md"))
            self.state.mark_task_complete(task_id)
            return True
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False

    def run_phase_html(self) -> bool:
        if not self._should_run_phase("html"): return True
        task_id = self.state.create_or_start_task(self.workflow_id, "html")
        try:
            logger.info("--- Phase 6: HTML Generation ---")
            generator = ReportGenerator()
            refined_draft = os.path.join(self.topic_drafts_dir, "refined_draft.md")
            source_draft = refined_draft if os.path.exists(refined_draft) else os.path.join(self.topic_drafts_dir, "draft.md")
            review_json_path = os.path.join(self.topic_drafts_dir, "review.json")
            
            report_path = generator.generate(
                draft_path=source_draft,
                review_path=review_json_path if os.path.exists(review_json_path) else None,
                output_dir=self.topic_drafts_dir,
            )
            if not report_path:
                raise Exception("HTML generation failed.")
            self.state.log_artifact(task_id, "html_report", report_path)
            self.state.mark_task_complete(task_id)
            return True
        except Exception as e:
            self.state.mark_task_failed(task_id, str(e))
            return False

    def run_all(self, pre_selected_papers: Optional[List[Any]] = None):
        if not self.run_phase_planning(): return
        
        # Convert dicts from UI to PaperInfo if necessary
        if pre_selected_papers and len(pre_selected_papers) > 0 and isinstance(pre_selected_papers[0], dict):
            logger.info("Converting paper dicts from UI to PaperInfo objects.")
            converted = []
            for p in pre_selected_papers:
                # Map 'pdf_link' to 'pdf_url' if needed
                p_url = p.get('pdf_link') or p.get('pdf_url')
                converted.append(PaperInfo(
                    paper_id=p.get('paper_id', ''),
                    title=p.get('title', ''),
                    authors=p.get('authors', []),
                    year=str(p.get('year', '')),
                    abstract=p.get('abstract', ''),
                    url=p.get('url', ''),
                    pdf_url=p_url
                ))
            pre_selected_papers = converted

        # Initial cycle
        if not self.run_phase_retrieval(pre_selected_papers=pre_selected_papers): return
        if not self.run_phase_extraction(): return
        
        while self.loop_count <= self.max_loops:
            success, gaps = self.run_phase_analysis()
            if not success: return
            
            # Check for loopback trigger (gaps)
            if gaps and gaps.get("has_gaps") and self.loop_count < self.max_loops:
                self.loop_count += 1
                logger.info(f"--- Recursive Research Cycle {self.loop_count} ---")
                
                # Perform secondary retrieval using the 'secondary_query' from gaps
                secondary_query = gaps.get("secondary_query")
                if secondary_query:
                    # We run retrieval again but with the new query
                    if not self.run_phase_retrieval(query_override=secondary_query): break
                    if not self.run_phase_extraction(): break
                    continue # Run analysis again on combined data
            
            break # No gaps or hit limit
            
        if not self.run_phase_drafting(): return
        if not self.run_phase_review(): return
        if not self.run_phase_html(): return
        self.state.update_workflow_status(self.workflow_id, "COMPLETED")
        logger.info("Workflow execution finished successfully.")


def main():
    parser = argparse.ArgumentParser(description="AI Research Tool - Stateful Multi-Agent Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    parser_run = subparsers.add_parser("run", help="Start or resume a topic workflow or review specific paper URL")
    parser_run.add_argument("topic", type=str, nargs="?", default="", help="Research topic OR direct paper web/PDF URL")
    parser_run.add_argument("--url", type=str, default="", help="Direct paper URL(s) to review (web link or PDF, comma-separated)")
    parser_run.add_argument("--limit", type=int, default=3, help="Number of papers to retrieve (default: 3)")
    parser_run.add_argument("--engine", type=str, default="langgraph", choices=["langgraph", "legacy"], help="Execution engine (default: langgraph)")
    parser_run.add_argument("--max-revisions", type=int, default=1, help="Maximum AI peer-review revision iterations (default: 1)")

    # rerun command
    parser_rerun = subparsers.add_parser("rerun", help="Rerun a specific phase for a topic and cascade")
    parser_rerun.add_argument("topic", type=str, help="Research topic")
    parser_rerun.add_argument("--phase", type=str, required=True, choices=["retrieval", "extraction", "analysis", "drafting", "review", "html"], help="Phase to rerun")

    # ui command (Modern Web Dashboard)
    parser_ui = subparsers.add_parser("ui", help="Start the interactive modern Web Dashboard")
    parser_ui.add_argument("--port", type=int, default=5001, help="Server port (default: 5001)")

    # gradio command (Gradio UI for Milestone 4)
    parser_gradio = subparsers.add_parser("gradio", help="Start the Milestone 4 Gradio interface")
    parser_gradio.add_argument("--port", type=int, default=7860, help="Gradio port (default: 7860)")
    parser_gradio.add_argument("--share", action="store_true", help="Create public shareable link")

    # graph command (Display & Export Architecture Diagram)
    parser_graph = subparsers.add_parser("graph", help="Visualize and export the LangGraph state architecture")
    parser_graph.add_argument("--export", type=str, default="docs/architecture_graph.png", help="Export path for diagram PNG")

    args = parser.parse_args()

    if args.command == "ui":
        start_server(port=args.port)
        return

    if args.command == "gradio":
        from src.ui.gradio_app import launch_gradio
        launch_gradio(port=args.port, share=getattr(args, "share", False))
        return

    if args.command == "graph":
        from src.graph.workflow import get_mermaid_graph, export_graph_image
        print("\n--- LangGraph Architecture (Mermaid) ---\n")
        print(get_mermaid_graph())
        if args.export:
            exported = export_graph_image(args.export)
            if exported:
                print(f"\nGraph diagram exported to: {args.export}")
        return

    if args.command == "run":
        target = args.url.strip() if args.url.strip() else args.topic.strip()
        if not target:
            parser_run.error("Please specify a research topic or paper link (e.g. python main.py run 'https://arxiv.org/abs/1706.03762')")

        urls = [u.strip() for u in args.url.split(",") if u.strip()] if args.url else []
        topic_str = args.topic if args.topic else target

        if args.engine == "langgraph":
            from src.graph.workflow import run_research_workflow
            print(f"\n--- Launching LangGraph Workflow for: '{target}' ---")
            result = run_research_workflow(
                topic=topic_str,
                limit=args.limit,
                max_revisions=args.max_revisions,
                paper_urls=urls if urls else None,
            )
            report_path = result.get("html_report_path", "")
            print(f"\nResearch Workflow Complete!")
            if report_path:
                print(f"HTML Report generated at: {report_path}")
            print(f"Launch Web Dashboard: python main.py ui")
            print(f"Launch Gradio UI:     python main.py gradio\n")
            return
        else:
            orch = PipelineOrchestrator(topic_str, limit=args.limit)
            orch.run_all()
            if orch.state.get_or_create_workflow(orch.topic_name, orch.slug)['status'] == 'COMPLETED':
                print(f"\nReport ready! Launch UI with:\n  python main.py ui")
            return

    if args.command == "rerun":
        orch = PipelineOrchestrator(args.topic)
        orch.state.reset_task(orch.workflow_id, args.phase)
        phases = ["retrieval", "extraction", "analysis", "drafting", "review", "html"]
        start_idx = phases.index(args.phase)
        for p in phases[start_idx:]:
            orch.state.reset_task(orch.workflow_id, p)
        orch.run_all()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user.")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
