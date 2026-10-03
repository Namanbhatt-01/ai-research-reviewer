"""
Gradio UI for the AI Systematic Research Reviewer.
Implements Milestone 4 requirements:
- Structured visualization of Abstract, Introduction, Methods, Results, Conclusion, References
- Interactive 'Critique / Revise' button for on-demand refinement loops
- Architecture graph visualization
- Exportable research reports
"""

import os
import json
import gradio as gr
from typing import Dict, Any, Tuple

from src.graph.workflow import run_research_workflow, get_mermaid_graph
from src.core.reviewer import DraftReviewer
from src.core.drafting import SectionDrafter
from src.config import config
from src.utils.logger import logger


def run_pipeline(topic: str, limit: int, max_revisions: int) -> Tuple[str, str, str, str, str, str]:
    """Runs the LangGraph research workflow and returns outputs for all tabs."""
    if not topic.strip():
        return (
            "Please provide a valid research topic.",
            "",
            "",
            "",
            "",
            "",
        )

    logger.info(f"[Gradio UI] Running pipeline for '{topic}'")
    try:
        result = run_research_workflow(topic.strip(), limit=limit, max_revisions=max_revisions)

        # Tab 1: Strategy
        plan = result.get("plan", {})
        strategy_md = f"### Research Strategy for: *{topic}*\n\n"
        if plan:
            strategy_md += f"**Refined Topic:** {plan.get('refined_topic', topic)}\n\n"
            strategy_md += f"**Structural Goal:** {plan.get('structural_goal', 'N/A')}\n\n"
            queries = plan.get("optimized_queries", [])
            strategy_md += "**Optimized Queries:**\n" + "\n".join(f"- `{q}`" for q in queries) + "\n\n"
            questions = plan.get("key_questions", [])
            strategy_md += "**Key Questions:**\n" + "\n".join(f"- {q}" for q in questions) + "\n"
        else:
            strategy_md += "_No strategy generated._"

        # Tab 2: Papers
        papers = result.get("selected_articles", [])
        papers_md = f"### Selected Academic Papers ({len(papers)})\n\n"
        for i, p in enumerate(papers, 1):
            title = p.get("title", "Untitled")
            authors = ", ".join(p.get("authors", [])) or "Unknown Authors"
            year = p.get("year", "N/A")
            pdf = p.get("pdf_link") or p.get("url") or "#"
            abstract = p.get("abstract", "No abstract available.")
            papers_md += f"#### {i}. [{title}]({pdf})\n"
            papers_md += f"**Authors:** {authors} | **Year:** {year}\n\n"
            papers_md += f"> {abstract[:400]}...\n\n---\n"

        # Tab 3: Findings
        findings = result.get("findings", {})
        findings_md = "### Extracted Key Findings & Comparison\n\n"
        comparison = result.get("comparison", "")
        if comparison:
            findings_md += f"#### Cross-Paper Synthesis\n{comparison}\n\n---\n"
        for fname, f_data in findings.items():
            if isinstance(f_data, dict):
                findings_md += f"#### Source: `{fname}`\n"
                for k, v in f_data.items():
                    key_title = k.replace("_", " ").title()
                    findings_md += f"- **{key_title}:** {v}\n"
                findings_md += "\n"

        # Tab 4: Draft
        final_draft = result.get("final_draft") or result.get("aggregated_draft") or "_No draft generated._"

        # Tab 5: Review
        review = result.get("review", {})
        review_md = "### Peer-Review Quality Assessment\n\n"
        if review:
            overall = review.get("overall_score", "N/A")
            review_md += f"**Overall Score:** `{overall} / 10.0`\n\n"
            sections = review.get("sections", {})
            for sname, sdata in sections.items():
                review_md += f"#### Section: {sname} (Score: {sdata.get('overall', 'N/A')}/10)\n"
                for dim in ["clarity", "academic_rigor", "completeness", "citation_usage"]:
                    if dim in sdata:
                        d = sdata[dim]
                        review_md += f"- **{dim.replace('_', ' ').title()}:** {d.get('score', 'N/A')}/10 — _{d.get('feedback', '')}_\n"
                review_md += "\n"
        else:
            review_md += "_No critique data available._"

        # Report path
        html_path = result.get("html_report_path", "")
        status_msg = f"Status: COMPLETED. HTML Report generated at: `{html_path}`"

        return (
            status_msg,
            strategy_md,
            papers_md,
            findings_md,
            final_draft,
            review_md,
        )
    except Exception as e:
        logger.error(f"[Gradio UI] Error: {e}", exc_info=True)
        return (f"Error: {e}", "", "", "", "", "")


def on_critique_revise(current_draft: str) -> Tuple[str, str]:
    """Allows on-demand user-triggered 'Critique / Revise' re-run as required by Milestone 4."""
    if not current_draft or len(current_draft.strip()) < 50:
        return "Draft is empty. Run the pipeline first.", current_draft

    logger.info("[Gradio UI] Triggering interactive Critique/Revise cycle...")
    try:
        reviewer = DraftReviewer()
        # Evaluate sections in memory
        review_summary = {"sections": {}, "overall_score": 0.0}
        sections_dict = {}
        curr_section = None
        curr_lines = []

        for line in current_draft.split("\n"):
            if line.startswith("## "):
                if curr_section and curr_lines:
                    sections_dict[curr_section] = "\n".join(curr_lines).strip()
                curr_section = line[3:].strip()
                curr_lines = []
            else:
                curr_lines.append(line)
        if curr_section and curr_lines:
            sections_dict[curr_section] = "\n".join(curr_lines).strip()

        scores = []
        revised_sections = {}
        critique_output = "### Interactive Critique & Revision Results\n\n"

        for name, text in sections_dict.items():
            ev = reviewer.evaluate_section(name, text)
            score = ev.get("overall", 8.0)
            scores.append(score)
            critique_output += f"**{name} Score:** `{score} / 10`\n"

            if score < config.REVIEW_PASSING_SCORE:
                critique_output += f"- _Status:_ Below threshold ({config.REVIEW_PASSING_SCORE}). Auto-refining...\n"
                suggestions = reviewer.suggest_revisions(name, text, ev)
                refined = reviewer.refine_section(name, text, suggestions)
                revised_sections[name] = refined or text
                critique_output += f"- _Action:_ Section rewritten with enhanced clarity and rigor.\n\n"
            else:
                revised_sections[name] = text
                critique_output += f"- _Status:_ Meets quality threshold.\n\n"

        avg_score = sum(scores) / len(scores) if scores else 10.0
        critique_output = f"**Overall Revision Score:** `{avg_score:.1f} / 10.0`\n\n" + critique_output

        # Rebuild draft
        lines = ["# Systematic Literature Review (Revised)\n"]
        for name, text in revised_sections.items():
            lines.append(f"## {name}\n")
            lines.append(text + "\n")
        new_draft = "\n".join(lines)

        return critique_output, new_draft
    except Exception as e:
        logger.error(f"[Gradio UI] Critique/Revise failed: {e}", exc_info=True)
        return f"Critique error: {e}", current_draft


def create_gradio_app():
    """Builds the Gradio interface."""
    with gr.Blocks(title="AI Research Paper Reviewer") as demo:
        gr.Markdown(
            """
            # 🔬 AI System to Automatically Review and Summarize Research Papers
            ### *Stateful Multi-Agent Literature Review Workflow (Infosys Springboard Internship)*
            Automates the entire systematic review lifecycle: **Research Planning → Smart Search → PyMuPDF4LLM Extraction → Multi-Paper Synthesis → AI Peer-Review Loop**.
            """
        )

        with gr.Row():
            with gr.Column(scale=3):
                topic_input = gr.Textbox(
                    label="Research Topic / Query",
                    placeholder="e.g., Quantum Key Distribution protocols in satellite communications",
                    value="Quantum Cryptography in Satellite Communications",
                )
            with gr.Column(scale=1):
                limit_slider = gr.Slider(minimum=1, maximum=5, value=3, step=1, label="Max Papers")
            with gr.Column(scale=1):
                rev_slider = gr.Slider(minimum=0, maximum=3, value=1, step=1, label="Max AI Revisions")

        with gr.Row():
            run_btn = gr.Button("🚀 Run Autonomous Review", variant="primary", scale=2)
            critique_btn = gr.Button("✍️ Critique / Revise Draft", variant="secondary", scale=1)

        status_box = gr.Markdown("**Status:** Ready.")

        with gr.Tabs():
            with gr.TabItem("📄 Systematic Review Draft"):
                draft_box = gr.Markdown(label="Generated Research Draft")
            with gr.TabItem("🔍 Peer-Review & Critique"):
                review_box = gr.Markdown(label="Quality Scores & Feedback")
            with gr.TabItem("📊 Key Findings & Comparison"):
                findings_box = gr.Markdown(label="Cross-Paper Findings")
            with gr.TabItem("📚 Selected Papers"):
                papers_box = gr.Markdown(label="Retrieved Academic Papers")
            with gr.TabItem("🎯 Research Strategy"):
                strategy_box = gr.Markdown(label="Planning & Optimized Queries")
            with gr.TabItem("🌐 Architecture Graph"):
                gr.Markdown("### LangGraph StateGraph Architecture")
                mermaid_code = get_mermaid_graph()
                gr.Markdown(f"```mermaid\n{mermaid_code}\n```")
                if os.path.exists("docs/architecture_graph.png"):
                    gr.Image("docs/architecture_graph.png", label="Compiled LangGraph Execution Flow")

        # Event Handlers
        run_btn.click(
            fn=run_pipeline,
            inputs=[topic_input, limit_slider, rev_slider],
            outputs=[status_box, strategy_box, papers_box, findings_box, draft_box, review_box],
        )

        critique_btn.click(
            fn=on_critique_revise,
            inputs=[draft_box],
            outputs=[review_box, draft_box],
        )

    return demo


def launch_gradio(port: int = 7860, share: bool = False):
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=port, share=share)


if __name__ == "__main__":
    launch_gradio()
