from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.retrieval import PaperInfo


class APAFormatter:
    """
    Formats academic paper metadata into APA 7th-edition style citations.

    APA pattern used:
        Author, A. A., & Author, B. B. (Year). *Title*. Retrieved from URL

    Rules applied:
        - 1 author  : Smith, J. A. (Year). ...
        - 2 authors : Smith, J. A., & Doe, B. (Year). ...
        - 3+authors : Smith, J. A., et al. (Year). ...
        - Unknown   : Anonymous. (Year). ...
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def format_citation(self, paper: "PaperInfo") -> str:
        """
        Returns a full APA reference string for a single paper.

        Example:
            Vaswani, A., et al. (2017). *Attention Is All You Need*.
            Retrieved from https://arxiv.org/abs/1706.03762
        """
        author_str = self._format_authors(paper.authors)
        year = paper.year or "n.d."
        title = paper.title.strip() if paper.title else "Untitled"
        url = paper.url or paper.pdf_url or ""

        citation = f"{author_str} ({year}). *{title}*."
        if url:
            citation += f" Retrieved from {url}"
        return citation

    def in_text(self, paper: "PaperInfo") -> str:
        """
        Returns a short APA in-text citation string.

        Example:  (Vaswani et al., 2017)
        """
        year = paper.year or "n.d."
        authors = paper.authors

        if not authors:
            return f"(Anonymous, {year})"

        first_last = self._last_name(authors[0])
        if len(authors) == 1:
            return f"({first_last}, {year})"
        elif len(authors) == 2:
            second_last = self._last_name(authors[1])
            return f"({first_last} & {second_last}, {year})"
        return f"({first_last} et al., {year})"

    def format_reference_list(self, papers: List["PaperInfo"]) -> str:
        """
        Returns an alphabetically sorted Markdown reference list.

        Each entry is prefixed with a number for easy linking.
        """
        if not papers:
            return "_No references available._"

        # Sort alphabetically by first author surname (or title if no author)
        def sort_key(p: "PaperInfo") -> str:
            if p.authors:
                return self._last_name(p.authors[0]).lower()
            return (p.title or "").lower()

        sorted_papers = sorted(papers, key=sort_key)

        lines = []
        for i, paper in enumerate(sorted_papers, start=1):
            lines.append(f"{i}. {self.format_citation(paper)}")

        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _last_name(full_name: str) -> str:
        """Extracts the last name from a full name string."""
        parts = full_name.strip().split()
        return parts[-1] if parts else full_name

    @staticmethod
    def _format_initial(full_name: str) -> str:
        """
        Converts a full name to 'Last, F. M.' APA author format.
        Example: 'John Andrew Smith' -> 'Smith, J. A.'
        """
        parts = full_name.strip().split()
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]

        last = parts[-1]
        initials = " ".join(f"{p[0]}." for p in parts[:-1] if p)
        return f"{last}, {initials}"

    def _format_authors(self, authors: List[str]) -> str:
        """Formats author list according to APA 7th-edition rules."""
        if not authors:
            return "Anonymous"

        formatted = [self._format_initial(a) for a in authors if a.strip()]

        if len(formatted) == 1:
            return formatted[0]
        if len(formatted) == 2:
            return f"{formatted[0]}, & {formatted[1]}"
        # 3 or more authors → et al.
        return f"{formatted[0]}, et al."
