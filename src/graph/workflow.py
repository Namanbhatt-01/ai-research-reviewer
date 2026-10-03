"""
LangGraph StateGraph workflow definition for the Academic Paper Reviewer.
Faithfully reproduces the directed state graph architecture:
__start__ -> process_input -> planner -> researcher -> search_articles
-> article_decisions -> download_articles -> paper_analyzer
-> [write_abstract, write_conclusion, write_introduction, write_methods, write_references, write_results]
-> aggregate_paper -> critique_paper -> (search_articles | revise_paper | final_draft)
-> final_draft -> __end__
"""

import os
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END

from src.graph.state import ResearchState
from src.graph.nodes import (
    process_input,
    planner,
    researcher,
    search_articles,
    article_decisions,
    download_articles,
    paper_analyzer,
    write_abstract,
    write_conclusion,
    write_introduction,
    write_methods,
    write_references,
    write_results,
    aggregate_paper,
    critique_paper,
    revise_paper,
    final_draft,
)
from src.utils.logger import logger


def route_critique(state: ResearchState) -> Literal["search_articles", "revise_paper", "final_draft"]:
    """
    Evaluates conditional branches following critique_paper:
    1. If critical research gaps exist and search budget remains -> search_articles
    2. If draft quality is below threshold and revision budget remains -> revise_paper
    3. Otherwise -> final_draft
    """
    if state.get("needs_more_research") and state.get("search_cycle", 0) <= state.get("max_search_cycles", 1):
        logger.info("[Route] Routing back to 'search_articles' for secondary research loop.")
        return "search_articles"

    if state.get("needs_revision") and state.get("revision_count", 0) < state.get("max_revisions", 2):
        logger.info("[Route] Routing to 'revise_paper' for iterative draft refinement.")
        return "revise_paper"

    logger.info("[Route] Quality criteria satisfied. Proceeding to 'final_draft'.")
    return "final_draft"


def build_research_graph() -> StateGraph:
    """Constructs and compiles the full LangGraph state graph."""
    builder = StateGraph(ResearchState)

    # 1. Register all 16 nodes
    builder.add_node("process_input", process_input)
    builder.add_node("planner", planner)
    builder.add_node("researcher", researcher)
    builder.add_node("search_articles", search_articles)
    builder.add_node("article_decisions", article_decisions)
    builder.add_node("download_articles", download_articles)
    builder.add_node("paper_analyzer", paper_analyzer)

    # Parallel writing nodes
    builder.add_node("write_abstract", write_abstract)
    builder.add_node("write_conclusion", write_conclusion)
    builder.add_node("write_introduction", write_introduction)
    builder.add_node("write_methods", write_methods)
    builder.add_node("write_references", write_references)
    builder.add_node("write_results", write_results)

    # Aggregator & Evaluation nodes
    builder.add_node("aggregate_paper", aggregate_paper)
    builder.add_node("critique_paper", critique_paper)
    builder.add_node("revise_paper", revise_paper)
    builder.add_node("final_draft", final_draft)

    # 2. Add sequential linear edges
    builder.add_edge(START, "process_input")
    builder.add_edge("process_input", "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "search_articles")
    builder.add_edge("search_articles", "article_decisions")
    builder.add_edge("article_decisions", "download_articles")
    builder.add_edge("download_articles", "paper_analyzer")

    # 3. Add parallel fan-out edges from paper_analyzer
    builder.add_edge("paper_analyzer", "write_abstract")
    builder.add_edge("paper_analyzer", "write_conclusion")
    builder.add_edge("paper_analyzer", "write_introduction")
    builder.add_edge("paper_analyzer", "write_methods")
    builder.add_edge("paper_analyzer", "write_references")
    builder.add_edge("paper_analyzer", "write_results")

    # 4. Add fan-in edges converging into aggregate_paper
    builder.add_edge("write_abstract", "aggregate_paper")
    builder.add_edge("write_conclusion", "aggregate_paper")
    builder.add_edge("write_introduction", "aggregate_paper")
    builder.add_edge("write_methods", "aggregate_paper")
    builder.add_edge("write_references", "aggregate_paper")
    builder.add_edge("write_results", "aggregate_paper")

    # 5. Connect aggregate_paper to critique_paper
    builder.add_edge("aggregate_paper", "critique_paper")

    # 6. Conditional cyclic edges from critique_paper
    builder.add_conditional_edges(
        "critique_paper",
        route_critique,
        {
            "search_articles": "search_articles",
            "revise_paper": "revise_paper",
            "final_draft": "final_draft",
        },
    )

    # 7. Revision loop edge back to critique_paper
    builder.add_edge("revise_paper", "critique_paper")

    # 8. Final draft terminates at END
    builder.add_edge("final_draft", END)

    return builder


# Global compiled app
research_app = build_research_graph().compile()


def run_research_workflow(topic: str, limit: int = 3, max_revisions: int = 2) -> Dict[str, Any]:
    """Runs the LangGraph research workflow for a given academic topic."""
    initial_state: ResearchState = {
        "topic": topic,
        "limit": limit,
        "max_revisions": max_revisions,
        "max_search_cycles": 1,
        "revision_count": 0,
        "search_cycle": 0,
    }
    logger.info(f"Starting LangGraph workflow for topic: '{topic}'")
    final_output = research_app.invoke(initial_state)
    logger.info(f"LangGraph workflow finished with status: {final_output.get('status')}")
    return final_output


def get_mermaid_graph() -> str:
    """Returns the Mermaid graph string representation of the architecture."""
    try:
        return research_app.get_graph().draw_mermaid()
    except Exception as e:
        logger.warning(f"Could not draw mermaid via LangGraph: {e}")
        return ""


def export_graph_image(output_path: str = "docs/architecture_graph.png") -> bool:
    """Exports graph visualization to PNG if graphviz or pygraphviz is available."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img_bytes = research_app.get_graph().draw_mermaid_png()
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        logger.info(f"Graph image saved to {output_path}")
        return True
    except Exception as e:
        logger.info(f"PNG export skipped (requires mermaid.ink or graphviz): {e}")
        return False
