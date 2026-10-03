import pytest
from src.core.retrieval import PaperRetriever, PaperInfo


def test_is_url_detection():
    """Verify PaperRetriever accurately detects various link formats vs topics."""
    assert PaperRetriever.is_url("https://arxiv.org/abs/1706.03762") is True
    assert PaperRetriever.is_url("https://arxiv.org/pdf/1706.03762.pdf") is True
    assert PaperRetriever.is_url("http://example.com/research_paper.pdf") is True
    assert PaperRetriever.is_url("arxiv:2301.12345") is True
    assert PaperRetriever.is_url("1706.03762") is True
    assert PaperRetriever.is_url("10.1038/nature12345") is True
    
    # Non-URLs
    assert PaperRetriever.is_url("Quantum Key Distribution in Satellite Networks") is False
    assert PaperRetriever.is_url("Transformers in Vision") is False
    assert PaperRetriever.is_url("Reinforcement Learning from Human Feedback") is False


def test_paper_info_serialization():
    """Ensure PaperInfo converts to dictionary with expected keys."""
    paper = PaperInfo(
        paper_id="test_01",
        title="Attention Is All You Need",
        authors=["Vaswani, Ashish", "Shazeer, Noam"],
        year="2017",
        abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        url="https://arxiv.org/abs/1706.03762",
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf"
    )
    d = paper.to_dict()
    assert d["paper_id"] == "test_01"
    assert d["title"] == "Attention Is All You Need"
    assert len(d["authors"]) == 2
    assert d["year"] == "2017"
    assert d["pdf_link"] == "https://arxiv.org/pdf/1706.03762.pdf"


def test_resolve_arxiv_paper_from_url():
    """Verify live metadata resolution from arXiv abstract link."""
    retriever = PaperRetriever()
    paper = retriever.resolve_paper_from_url("https://arxiv.org/abs/1706.03762")
    assert paper is not None
    assert "Attention Is All You Need" in paper.title
    assert paper.year == "2017"
    assert "Vaswani" in paper.authors[0] or "Ashish" in paper.authors[0]
    assert paper.pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"
