import pytest
from src.api.app import app
from src.ui.gradio_app import on_critique_revise
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


def test_gradio_critique_revise_function():
    """Verify on_critique_revise interactive function in Gradio app."""
    sample_draft = (
        "# Literature Review\n\n"
        "## Abstract\n"
        "This paper explores neural architectures and transformers in sequence transduction.\n\n"
        "## Methods\n"
        "We evaluate self-attention against recurrence.\n\n"
        "## Results\n"
        "Demonstrated 28.4 BLEU score on WMT benchmark.\n\n"
        "## Conclusion\n"
        "Transformers represent a promising foundation for sequence tasks.\n"
    )
    
    critique_output, revised_draft = on_critique_revise(sample_draft)
    assert "Overall Revision Score:" in critique_output
    assert revised_draft is not None
    assert "## Abstract" in revised_draft
    assert "## Methods" in revised_draft
