import os
from dataclasses import dataclass, field
from typing import Optional, List
import itertools
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    """
    Centralized configuration management.

    Keys used across the three in-scope phases:
      Phase 1 — Paper retrieval (Semantic Scholar / ArXiv, PDF download, metadata)
      Phase 2 — Text extraction (PDF → Markdown)
      Phase 3 — Key-finding extraction and cross-paper comparison
    """
    # --- API ---
    OPENAI_API_KEYS: List[str] = field(default_factory=lambda: [k.strip() for k in os.getenv("OPENAI_API_KEY", "").split(",") if k.strip()])
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    APP_API_KEY: str = os.getenv("APP_API_KEY", "research_secret_123")  # New authentication key
    
    _key_cycle = None
    
    @classmethod
    def get_next_api_key(cls) -> str:
        """Returns the next API key in the round-robin pool to avoid rate limits."""
        if cls._key_cycle is None:
            keys = [k.strip() for k in os.getenv("OPENAI_API_KEY", "").split(",") if k.strip()]
            cls._key_cycle = itertools.cycle(keys) if keys else itertools.cycle([""])
        return next(cls._key_cycle)

    # --- Resource Limits ---
    MAX_PDF_SIZE_MB: int = int(os.getenv("MAX_PDF_SIZE_MB", 30))
    MIN_FREE_DISK_MB: int = int(os.getenv("MIN_FREE_DISK_MB", 500))

    # --- Directories ---
    RAW_PDF_DIR: str = os.path.join("data", "raw_pdfs")
    PROCESSED_TEXT_DIR: str = os.path.join("data", "processed_text")
    ANALYSIS_DIR: str = os.path.join("data", "analysis")
    METADATA_DIR: str = os.path.join("data", "metadata")
    DRAFTS_DIR: str = os.path.join("data", "drafts")

    # --- Retrieval limits ---
    ARXIV_LIMIT_DEFAULT: int = 3

    # --- Review & refinement ---
    REVIEW_PASSING_SCORE: int = 7   # sections scoring below this are auto-refined

    @classmethod
    def validate(cls):
        """Ensures critical configurations are present."""
        if not os.getenv("OPENAI_API_KEY"):
            print("Warning: OPENAI_API_KEY not found in environment.")
            return False
        return True

config = Config()
