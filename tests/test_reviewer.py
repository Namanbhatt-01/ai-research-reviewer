import pytest
from src.core.reviewer import DraftReviewer, REVIEWABLE_SECTIONS


def test_reviewable_sections_list():
    """Verify all 6 academic sections are listed in reviewable sections."""
    assert "Abstract" in REVIEWABLE_SECTIONS
    assert "Introduction" in REVIEWABLE_SECTIONS
    assert "Methods" in REVIEWABLE_SECTIONS
    assert "Results" in REVIEWABLE_SECTIONS
    assert "Conclusion" in REVIEWABLE_SECTIONS


def test_evaluate_section_heuristics():
    """Verify DraftReviewer computes structured scores across all 4 required dimensions."""
    reviewer = DraftReviewer()
    sample_text = (
        "This study investigates neural network efficiency under distributed settings (Vaswani et al., 2017). "
        "However, significant limitations remain regarding memory bandwidth and scaling bottlenecks. "
        "In contrast to sequential models, self-attention improves parallel throughput substantially. "
        "The empirical results confirm a 4x reduction in training latency across standard benchmark tasks. "
        "Nonetheless, communication overhead presents an ongoing architectural challenge that requires future inquiry."
    )
    
    evaluation = reviewer.evaluate_section("Methods", sample_text)
    
    assert "clarity" in evaluation
    assert "academic_rigor" in evaluation
    assert "completeness" in evaluation
    assert "citation_usage" in evaluation
    assert "overall" in evaluation
    
    assert 0 <= evaluation["overall"] <= 10
    assert evaluation["citation_usage"]["score"] >= 6  # Found (Vaswani et al., 2017)


def test_reviewer_flags_short_sections():
    """Verify that brief sections receive lower completeness scores."""
    reviewer = DraftReviewer()
    short_text = "This is a very brief summary of the method."
    evaluation = reviewer.evaluate_section("Methods", short_text)
    assert evaluation["completeness"]["score"] < 5
