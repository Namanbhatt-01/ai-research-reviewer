import pytest
from src.api.app import app
from src.core.reviewer import DraftReviewer
from src.config import config


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_flask_index_page(client):
    """Verify Flask web dashboard responds on root route."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"AI Research" in response.data or b"Dashboard" in response.data


def test_flask_history_endpoint(client):
    """Verify research history endpoint with API key authorization."""
    response = client.get(
        "/api/research/history",
        headers={"X-API-Key": config.APP_API_KEY}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_reviewer_heuristic_evaluation():
    """Verify DraftReviewer heuristic evaluation calculates structured quality scores."""
    reviewer = DraftReviewer()
    sample_text = (
        "This systematic review analyzes recent progress in transformer architectures "
        "and self-attention mechanisms in sequence transduction. Empirical results across "
        "multiple benchmarks demonstrate significant improvements over recurrent models."
    )
    evaluation = reviewer.evaluate_section("Abstract", sample_text)
    assert "overall" in evaluation
    assert 0 <= evaluation["overall"] <= 10
    assert "clarity" in evaluation
    assert "academic_rigor" in evaluation

