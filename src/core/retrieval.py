import os
import json
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Optional, Dict, Any
from src.config import config
from src.utils.logger import logger


class PaperInfo:
    """A standardized container for academic paper data."""

    def __init__(
        self,
        paper_id: str,
        title: str,
        authors: List[str],
        year: str,
        abstract: str,
        url: str,
        pdf_url: Optional[str],
    ):
        self.paper_id = paper_id
        self.title = title
        self.authors = authors
        self.year = year
        self.abstract = abstract
        self.url = url
        self.pdf_url = pdf_url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "url": self.url,
            "pdf_link": self.pdf_url,
        }


class PaperRetriever:
    """
    Handles academic paper search and download.

    Search strategy:
      1. Semantic Scholar API (primary) — open, no auth required.
      2. ArXiv API (fallback)           — used when Semantic Scholar returns nothing.
    """

    SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    ARXIV_SEARCH_URL = "http://export.arxiv.org/api/query"

    def __init__(self, user_agent: str = "ResearchTool/2.0"):
        self.headers = {"User-Agent": user_agent}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Configure robust exponential backoff for API rate limits and network hiccups
        retries = Retry(
            total=5,
            backoff_factor=2.0,  # Delays: 0s, 2s, 4s, 8s, 16s, 32s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def search_papers(self, query: str, limit: int = 3, bypass_cache: bool = False) -> tuple[List[PaperInfo], bool]:
        """
        Search for papers by topic.
        Tries ArXiv first; falls back to Semantic Scholar if ArXiv returns nothing.
        Returns (papers, was_cached).
        """
        if not bypass_cache:
            from src.config import config
            import re
            slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
            cached_metadata = os.path.join(config.METADATA_DIR, slug, "papers.json")
            if os.path.exists(cached_metadata):
                logger.info("Found cached metadata. Skipping network search.")
                try:
                    with open(cached_metadata, "r") as f:
                        data = json.load(f)
                    return_list = []
                    for p in data:
                        return_list.append(PaperInfo(
                            paper_id=p["paper_id"],
                            title=p["title"],
                            authors=p["authors"],
                            year=p["year"],
                            abstract=p["abstract"],
                            url=p["url"],
                            pdf_url=p["pdf_link"]
                        ))
                    return return_list, True
                except json.JSONDecodeError as e:
                    logger.warning(f"Corrupted cache file found at {cached_metadata}, ignoring. Error: {e}")
                except Exception as e:
                    logger.error(f"Error reading cache file {cached_metadata}: {e}")

        papers = self.search_arxiv(query, limit)
        if not papers:
            logger.warning("ArXiv returned no results. Falling back to Semantic Scholar.")
            papers = self._search_semantic_scholar(query, limit)
        return papers, False

    def download_papers(self, papers: List[PaperInfo], folder: str) -> List[str]:
        """Downloads multiple papers and returns paths to those successful."""
        paths = []
        for p in papers:
            path = self.download_pdf(p, folder)
            if path:
                paths.append(path)
        return paths

    def save_metadata(self, papers: List[PaperInfo], folder: str = config.METADATA_DIR, append: bool = False) -> None:
        """Saves paper details to a JSON file. If append=True, merges with existing file."""
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, "papers.json")
        
        new_data = [p.to_dict() for p in papers]
        
        if append and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                # Avoid duplicates by title
                existing_titles = {p["title"] for p in existing_data}
                filtered_new = [p for p in new_data if p["title"] not in existing_titles]
                new_data = existing_data + filtered_new
                logger.info(f"Appending {len(filtered_new)} new papers to existing metadata.")
            except Exception as e:
                logger.warning(f"Failed to read existing metadata for append: {e}")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=4)
            logger.info(f"Metadata saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def download_pdf(self, paper: PaperInfo, folder: str = config.RAW_PDF_DIR) -> Optional[str]:
        """Downloads the PDF for a paper if a link is available."""
        if not paper.pdf_url:
            logger.warning(f"No PDF link available for: {paper.title}")
            return None

        os.makedirs(folder, exist_ok=True)

        # Sanitize filename
        safe_title = "".join(c if c.isalnum() else "_" for c in paper.title)[:40]
        filename = f"{safe_title}_{paper.paper_id}.pdf"
        path = os.path.join(folder, filename)

        if os.path.exists(path):
            logger.info(f"PDF already exists, skipping download: {filename}")
            return path

        # 1. Disk Space Check
        import shutil
        total, used, free = shutil.disk_usage(folder)
        free_mb = free / (1024 * 1024)
        if free_mb < config.MIN_FREE_DISK_MB:
            logger.error(f"Insufficient disk space ({free_mb:.1f} MB remaining). Aborting download.")
            return None

        logger.info(f"Downloading: {paper.title} ...")
        downloaded_bytes = 0
        max_bytes = config.MAX_PDF_SIZE_MB * 1024 * 1024
        
        try:
            r = self.session.get(paper.pdf_url, stream=True, timeout=30)
            r.raise_for_status()
            
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk: continue
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > max_bytes:
                        raise ValueError(f"PDF exceeds maximum allowed size ({config.MAX_PDF_SIZE_MB}MB).")
                    f.write(chunk)
                    
            logger.info(f"PDF saved to: {path}")
            return path
        except Exception as e:
            logger.error(f"Error downloading '{paper.title}': {e}")
            # Automatic Cleanup: remove partial files to prevent parser errors later
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Cleaned up partial/corrupted download: {path}")
                except Exception as clean_err:
                    logger.error(f"Failed to clean up partial file: {clean_err}")
            return None

    # ------------------------------------------------------------------
    # Private search backends
    # ------------------------------------------------------------------

    def _search_semantic_scholar(self, query: str, limit: int) -> List[PaperInfo]:
        """Search via the Semantic Scholar Graph API (no API key required)."""
        logger.info(f"Searching Semantic Scholar for: '{query}' (limit: {limit})")
        params = {
            "query": query,
            "limit": limit,
            "fields": "paperId,title,authors,year,abstract,openAccessPdf,externalIds,url",
        }
        try:
            response = self.session.get(
                self.SEMANTIC_SCHOLAR_SEARCH_URL,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()

            papers: List[PaperInfo] = []
            for item in data.get("data", []):
                paper_id = item.get("paperId", "")
                title = (item.get("title") or "Untitled").strip()
                year = str(item.get("year") or "")
                abstract = (item.get("abstract") or "").strip()
                url = item.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}"
                authors = [
                    a.get("name", "") for a in item.get("authors", []) if a.get("name")
                ]

                # Prefer open-access PDF; try ArXiv as supplement
                pdf_url: Optional[str] = None
                oa = item.get("openAccessPdf") or {}
                if oa.get("url"):
                    pdf_url = oa["url"]
                else:
                    arxiv_id = (item.get("externalIds") or {}).get("ArXiv")
                    if arxiv_id:
                        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                papers.append(PaperInfo(paper_id, title, authors, year, abstract, url, pdf_url))

            logger.info(f"Semantic Scholar returned {len(papers)} paper(s).")
            return papers
        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")
            return []

    def search_arxiv(self, query: str, limit: int) -> List[PaperInfo]:
        """Search via the ArXiv Atom/XML API (fallback)."""
        logger.info(f"Searching ArXiv for: '{query}' (limit: {limit})")
        url = f"{self.ARXIV_SEARCH_URL}?search_query=all:{query}&start=0&max_results={limit}"
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            papers: List[PaperInfo] = []
            for entry in root.findall("atom:entry", ns):
                title = (entry.find("atom:title", ns).text or "").strip()
                paper_id = (entry.find("atom:id", ns).text or "").split("/")[-1]
                published = (entry.find("atom:published", ns).text or "")[:4]
                abstract = (entry.find("atom:summary", ns).text or "").strip()
                url_link = entry.find("atom:id", ns).text or ""

                pdf_url: Optional[str] = None
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                        pdf_url = link.get("href")
                        if pdf_url and not pdf_url.endswith(".pdf"):
                            pdf_url += ".pdf"
                        break

                authors = [
                    a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)
                    if a.find("atom:name", ns) is not None
                ]

                papers.append(
                    PaperInfo(paper_id, title, authors, published, abstract, url_link, pdf_url)
                )

            logger.info(f"ArXiv returned {len(papers)} paper(s).")
            return papers
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            return []
