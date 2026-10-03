"""
ResearchState definition for the LangGraph-based Academic Paper Reviewer.
"""
from typing import TypedDict, List, Dict, Any, Optional


class ResearchState(TypedDict, total=False):
    # Core inputs & settings
    topic: str
    slug: str
    limit: int
    workflow_id: Optional[int]
    paper_urls: Optional[List[str]]
    is_direct_url_mode: bool
    
    # State tracking
    current_step: str
    status: str
    logs: List[str]
    
    # Planning & Search
    plan: Optional[Dict[str, Any]]
    research_query: Optional[str]
    optimized_queries: List[str]
    raw_articles: List[Dict[str, Any]]
    selected_articles: List[Dict[str, Any]]
    downloaded_pdfs: List[str]
    extracted_texts: List[Dict[str, str]]
    
    # Analysis
    findings: Optional[Dict[str, Any]]
    comparison: Optional[str]
    
    # Parallel Draft Sections
    abstract: Optional[str]
    introduction: Optional[str]
    methods: Optional[str]
    results: Optional[str]
    conclusion: Optional[str]
    references: Optional[str]
    synthesis: Optional[str]
    
    # Aggregation & Review
    aggregated_draft: Optional[str]
    draft_path: Optional[str]
    review: Optional[Dict[str, Any]]
    review_path: Optional[str]
    
    # Loopback controls & counters
    revision_count: int
    max_revisions: int
    search_cycle: int
    max_search_cycles: int
    needs_more_research: bool
    secondary_query: Optional[str]
    needs_revision: bool
    
    # Final Output
    final_draft: Optional[str]
    final_draft_path: Optional[str]
    html_report_path: Optional[str]
