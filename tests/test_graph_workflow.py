import pytest
from src.graph.workflow import build_research_graph, get_mermaid_graph, route_critique
from src.graph.state import ResearchState
from src.graph.nodes import process_input, search_articles, article_decisions


def test_build_research_graph():
    """Verify LangGraph compiles without errors and includes all 16 architecture nodes."""
    graph = build_research_graph()
    app = graph.compile()
    assert app is not None
    
    mermaid_str = get_mermaid_graph()
    assert "process_input" in mermaid_str
    assert "planner" in mermaid_str
    assert "researcher" in mermaid_str
    assert "search_articles" in mermaid_str
    assert "article_decisions" in mermaid_str
    assert "download_articles" in mermaid_str
    assert "paper_analyzer" in mermaid_str
    assert "write_abstract" in mermaid_str
    assert "write_introduction" in mermaid_str
    assert "write_methods" in mermaid_str
    assert "write_results" in mermaid_str
    assert "write_conclusion" in mermaid_str
    assert "write_references" in mermaid_str
    assert "aggregate_paper" in mermaid_str
    assert "critique_paper" in mermaid_str
    assert "revise_paper" in mermaid_str
    assert "final_draft" in mermaid_str


def test_conditional_routing_critique():
    """Verify conditional edges follow the mentor's state machine logic."""
    # 1. Needs more research -> loops back to search_articles
    state_gap: ResearchState = {
        "needs_more_research": True,
        "search_cycle": 0,
        "max_search_cycles": 1,
        "needs_revision": False,
        "revision_count": 0,
        "max_revisions": 2
    }
    assert route_critique(state_gap) == "search_articles"

    # 2. Needs revision -> loops to revise_paper
    state_revise: ResearchState = {
        "needs_more_research": False,
        "needs_revision": True,
        "revision_count": 0,
        "max_revisions": 2
    }
    assert route_critique(state_revise) == "revise_paper"

    # 3. Passed / budget exhausted -> final_draft
    state_pass: ResearchState = {
        "needs_more_research": False,
        "needs_revision": False,
        "revision_count": 1,
        "max_revisions": 2
    }
    assert route_critique(state_pass) == "final_draft"


def test_process_input_direct_url_mode():
    """Verify process_input detects direct URL mode and resolves the paper metadata."""
    state: ResearchState = {
        "topic": "https://arxiv.org/abs/1706.03762",
        "limit": 1
    }
    out = process_input(state)
    assert out.get("is_direct_url_mode") is True
    assert "Attention Is All You Need" in out.get("topic", "")
    assert len(out.get("selected_articles", [])) == 1
    assert out["selected_articles"][0]["pdf_link"] == "https://arxiv.org/pdf/1706.03762.pdf"
