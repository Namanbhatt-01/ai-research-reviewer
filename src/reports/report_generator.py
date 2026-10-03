import os
import json
import re
from typing import Dict, Any, Optional

from src.config import config
from src.utils.logger import logger

try:
    import markdown2
    _MARKDOWN2_AVAILABLE = True
except ImportError:
    _MARKDOWN2_AVAILABLE = False
    logger.warning("markdown2 not installed — section text will render as plain text.")


# ── Inline HTML template ────────────────────────────────────────────────────
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  /* ── Reset & Modern Base ── */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg-color:      #f8fafc;
    --surface-color: rgba(255, 255, 255, 0.8);
    --text-primary:   #0f172a;
    --text-secondary: #475569;
    --border-color:   rgba(226, 232, 240, 0.6);
    --primary:        #4f46e5;
    --primary-hover:  #4338ca;
    --success:        #059669;
    --danger:         #dc2626;
    --pending:        #d97706;
    --accent-glow:    rgba(79, 70, 229, 0.1);
    --radius:         12px;
    --shadow:         0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
    --shadow-lg:      0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
  }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: 'Inter', -apple-system, sans-serif;
    background-color: var(--bg-color);
    background-image: 
        radial-gradient(at 0% 0%, hsla(243, 75%, 59%, 0.05) 0px, transparent 50%),
        radial-gradient(at 100% 0%, hsla(280, 75%, 59%, 0.05) 0px, transparent 50%),
        radial-gradient(at 100% 100%, hsla(243, 75%, 59%, 0.05) 0px, transparent 50%),
        radial-gradient(at 0% 100%, hsla(280, 75%, 59%, 0.05) 0px, transparent 50%);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}

  /* ── Research Context Strip (Now References Section) ── */

  .source-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.25rem; }}
  
  .source-card {{
    background: #ffffff;
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.5rem;
    transition: all 0.25s ease;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
  }}
  .source-card:hover {{
    border-color: #cbd5e1;
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.05);
  }}
  .source-card .tag {{ font-size: 0.725rem; font-weight: 600; padding: 4px 10px; border-radius: 6px; display: inline-block; letter-spacing: -0.01em; }}
  .tag.work {{ background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }}
  .tag.state-of-the-art {{ background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; }}
  .tag.advancement {{ background: #f8fafc; color: #475569; border: 1px solid #e2e8f0; }}

  .card-header-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
  .metadata-cluster {{ display: flex; align-items: center; gap: 1rem; }}
  
  .retrieval-source {{ font-size: 0.8rem; color: #64748b; font-weight: 500; display: flex; align-items: center; gap: 0.75rem; }}
  .retrieval-source a {{ color: #64748b; text-decoration: none; transition: color 0.15s; }}
  .retrieval-source a:hover {{ color: var(--primary); }}
  .spacer {{ width: 1px; height: 12px; background: #cbd5e1; display: inline-block; }}

  .btn-icon {{
    display: flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; border-radius: 8px;
    background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0;
    transition: all 0.2s ease; text-decoration: none;
  }}
  .btn-icon:hover {{ background: #ffffff; color: var(--primary); border-color: #cbd5e1; box-shadow: 0 2px 4px rgba(0,0,0,0.02); transform: translateY(-1px); }}

  .source-card h4 {{ font-size: 1.1rem; font-weight: 700; margin: 0; line-height: 1.4; color: #0f172a; letter-spacing: -0.015em; }}
  .source-card .card-authors {{ font-size: 0.85rem; color: #475569; margin: 0; line-height: 1.5; }}

  /* ── Header (Glassmorphism) ── */
  header {{
    position: sticky; top: 0; z-index: 1000;
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border-color);
    padding: 1rem 2rem;
    display: flex; align-items: center; justify-content: space-between;
  }}
  .brand {{ display: flex; align-items: center; gap: 0.85rem; }}
  .brand-icon {{ background: var(--accent-glow); padding: 0.5rem; border-radius: 10px; display: flex; }}
  .brand h1 {{ 
    font-size: 1.25rem; font-weight: 800; letter-spacing: -0.025em;
    color: #0f172a;
  }}
  .brand .subtitle {{ 
    font-size: 0.75rem; color: var(--text-secondary); font-weight: 600; 
    text-transform: uppercase; letter-spacing: 0.05em; margin-top: -2px;
  }}

  /* ── Layout Grid (Sidebar + Content) ── */
  .layout {{
    display: grid;
    grid-template-columns: 280px 1fr;
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem 2rem 4rem;
    gap: 3rem;
  }}
  @media (max-width: 1024px) {{
    .layout {{ grid-template-columns: 1fr; gap: 2rem; }}
    .sidebar {{ display: none; }}
  }}

  /* ── Sidebar TOC ── */
  .sidebar {{ position: sticky; top: 6rem; align-self: start; }}
  .toc {{
    background: white; border: 1px solid var(--border-color);
    border-radius: var(--radius); padding: 1.5rem; box-shadow: var(--shadow);
  }}
  .toc h3 {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 1rem; }}
  .toc ul {{ list-style: none; }}
  .toc li {{ margin-bottom: 0.5rem; }}
  .toc a {{
    display: block; padding: 0.5rem 0.75rem; border-radius: 8px;
    color: var(--text-secondary); text-decoration: none; font-size: 0.9rem; font-weight: 500;
    transition: all 0.2s;
  }}
  .toc a:hover {{ background: var(--bg-color); color: var(--primary); }}
  .toc a.active {{ background: var(--accent-glow); color: var(--primary); font-weight: 600; }}

  /* ── Main Content Area ── */
  .main-content {{ max-width: 900px; }}

  /* ── Score Strip ── */
  .summary-strip {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.25rem; margin-bottom: 2.5rem;
  }}
  .score-card {{
    background: white; border: 1px solid var(--border-color);
    border-radius: var(--radius); padding: 1.25rem;
    display: flex; flex-direction: column; gap: 0.5rem;
    box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05); transition: transform 0.2s, box-shadow 0.2s;
  }}
  .score-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow); }}
  .score-card .label {{ font-size: 0.7rem; font-weight: 700; text-transform: uppercase; color: var(--text-secondary); letter-spacing: 0.05em; }}
  .score-card .value {{ font-size: 1.75rem; font-weight: 800; color: var(--text-primary); }}
  .score-card .bar {{ height: 6px; border-radius: 99px; background: #f1f5f9; margin-top: 4px; overflow: hidden; }}
  .score-card .fill {{ height: 100%; border-radius: 99px; transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1); }}
  .pass  {{ color: var(--success); }} .fill-pass  {{ background: var(--success); }}
  .warn  {{ color: var(--pending); }} .fill-warn  {{ background: var(--pending); }}
  .fail  {{ color: var(--danger);  }} .fill-fail  {{ background: var(--danger); }}

  /* ── Section Cards ── */
  .section-card {{
    background: white; border: 1px solid var(--border-color);
    border-radius: var(--radius); padding: 3rem 3.5rem;
    box-shadow: var(--shadow); margin-bottom: 3rem;
  }}
  .section-card h2 {{
    font-size: 1.75rem; font-weight: 800; margin-bottom: 2rem;
    color: var(--text-primary); letter-spacing: -0.025em;
    border-bottom: 2px solid var(--bg-color); padding-bottom: 1rem;
  }}
  .section-card p  {{ margin-bottom: 1.5rem; color: #334155; line-height: 1.8; font-size: 1.05rem; }}
  .section-card ul, .section-card ol {{ padding-left: 1.5rem; margin-bottom: 1.5rem; }}
  .section-card li {{ margin-bottom: 0.75rem; color: #334155; font-size: 1.05rem; }}
  .section-card em {{ font-style: italic; color: var(--primary); }}
  .section-card strong {{ font-weight: 700; color: var(--text-primary); }}
  .section-card blockquote {{ border-left: 4px solid var(--primary); padding-left: 1.5rem; margin: 2rem 0; font-style: italic; color: var(--text-secondary); }}

  /* ── Interaction Elements ── */
  .refined-badge {{
    display: inline-flex; align-items: center; gap: 4px;
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 99px; padding: 2px 10px; font-size: 0.7rem;
    color: #2563eb; margin-left: 0.75rem; font-weight: 700;
    vertical-align: middle; text-transform: uppercase;
  }}

  /* ── Section Actions (collapsed by default) ── */
  .section-header-row {{
    display: flex; align-items: flex-start; justify-content: space-between;
    margin-bottom: 2rem;
  }}
  .section-header-row h2 {{ margin-bottom: 0; border-bottom: none; padding-bottom: 0; }}
  .section-action-btn {{
    flex-shrink: 0; margin-left: 1rem; margin-top: 0.25rem;
    width: 34px; height: 34px;
    background: var(--bg-color); border: 1px solid var(--border-color);
    border-radius: 8px; cursor: pointer; display: flex; align-items: center;
    justify-content: center; transition: all 0.2s; color: var(--text-secondary);
  }}
  .section-action-btn:hover {{ background: var(--accent-glow); border-color: var(--primary); color: var(--primary); transform: scale(1.05); }}
  .section-action-btn.active {{ background: var(--accent-glow); border-color: var(--primary); color: var(--primary); }}

  .section-extras {{ display: none; }}
  .section-extras.open {{ display: block; }}

  .suggestions-box {{
    margin-top: 2rem; background: #fffbeb; border: 1px solid #fef3c7;
    border-radius: 10px; padding: 1.5rem;
  }}
  .suggestion-heading {{ font-size: 0.75rem; font-weight: 800; text-transform: uppercase; color: #92400e; margin-bottom: 1rem; letter-spacing: 0.05em; display: flex; align-items: center; gap: 0.5rem; }}
  .suggestions-box li {{ font-size: 0.95rem; color: #92400e; margin-bottom: 0.6rem; }}

  .section-controls {{ margin-top: 1.5rem; display: flex; align-items: center; gap: 1rem; }}
  .btn-revise {{
    padding: 0.7rem 1.5rem; background-color: var(--text-primary);
    color: white; border: none; border-radius: 10px;
    font-weight: 700; cursor: pointer; transition: all 0.2s;
    font-size: 0.9rem; display: inline-flex; align-items: center; gap: 0.6rem;
  }}
  .btn-revise:hover:not(:disabled) {{ background-color: #334155; transform: translateY(-1px); box-shadow: var(--shadow); }}
  .btn-revise .icon {{ width: 16px; height: 16px; }}

  /* ── References Table ── */
  .ref-list {{ list-style: none; padding: 0; }}
  .ref-item {{
    padding: 1.25rem; border-bottom: 1px solid var(--bg-color);
    font-size: 0.95rem; color: #475569; display: flex; gap: 1.25rem; align-items: flex-start;
  }}
  .ref-item:last-child {{ border-bottom: none; }}
  .ref-num {{ color: var(--primary); font-weight: 800; font-size: 0.85rem; background: var(--accent-glow); padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }}
  .ref-item a {{ color: var(--primary); text-decoration: none; font-weight: 600; overflow-wrap: anywhere; }}
  .ref-item a:hover {{ text-decoration: underline; }}

  /* ── PDF Export Optimization ── */
  @media print {{
    header, .sidebar, .section-controls, .suggestions-box {{ display: none !important; }}
    .layout {{ display: block; }}
    .main-content {{ max-width: 100%; }}
    .section-card {{ border: none; box-shadow: none; padding: 0; margin-bottom: 4rem; page-break-inside: avoid; }}
    body {{ background: white; }}
  }}

  /* ── Footer ── */
  footer {{ text-align: center; font-size: 0.8rem; color: var(--text-secondary); padding: 2rem; border-top: 1px solid var(--border-color); margin-top: 2rem; }}
</style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-icon">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary)"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
    </div>
    <div>
      <h1>Systematic Review & Evidence Synthesis</h1>
      <div class="subtitle">Academic Literature Synthesis &bull; {subtitle}</div>
    </div>
  </div>
  <div style="font-size: 0.75rem; color: var(--text-secondary); font-weight: 600;">{date}</div>
</header>

<div class="layout">
  <!-- Sidebar Navigation -->
  <aside class="sidebar">
    <nav class="toc">
      <h3>Table of Contents</h3>
      <ul id="toc-list">
        <!-- JS generated -->
      </ul>
    </nav>
  </aside>

  <!-- Main Content -->
  <main class="main-content">
    {score_strip}
    <div id="sections-container">
      {tab_panels}
    </div>
    {context_html}
  </main>
</div>

<footer>&copy; Systematic Literature Review System &bull; PRISMA-Aligned Academic Evidence Synthesis &bull; {date}</footer>

<script>
  // Section Auto-Scroll & TOC Generation
  const sections = document.querySelectorAll('.section-card');
  const tocList = document.getElementById('toc-list');

  sections.forEach(section => {{
    const id = section.parentElement.id; // tab-id
    const title = section.querySelector('h2').firstChild.textContent.trim();
    
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = '#' + id;
    a.textContent = title;
    a.onclick = (e) => {{
        e.preventDefault();
        document.getElementById(id).scrollIntoView({{ behavior: 'smooth' }});
    }};
    li.appendChild(a);
    tocList.appendChild(li);
    
    // Convert Tab Panels to sequential Flow (removing display:none)
    section.parentElement.style.display = 'block';
  }});

  // Simple Scroll Highlight
  window.addEventListener('scroll', () => {{
    let current = "";
    sections.forEach(section => {{
      const sectionTop = section.offsetTop;
      if (pageYOffset >= sectionTop - 120) {{
        current = section.parentElement.id;
      }}
    }});
    document.querySelectorAll('.toc a').forEach(a => {{
      a.classList.remove('active');
      if (a.getAttribute('href') === '#' + current) {{
        a.classList.add('active');
      }}
    }});
  }});

  // Section action icon toggle
  document.querySelectorAll('.section-action-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const extras = btn.closest('.section-card').querySelector('.section-extras');
      const isOpen = extras.classList.toggle('open');
      btn.classList.toggle('active', isOpen);
      btn.title = isOpen ? 'Hide Editorial Notes' : 'Show Editorial Notes';
    }});
  }});

  // Revise button logic
  document.querySelectorAll('.btn-revise').forEach(btn => {{
    btn.addEventListener('click', async () => {{
      const sectionName = btn.dataset.section;
      const topic = "{topic_slug}";
      const apiKey = "{api_key}";
      
      if (!confirm(`Request editorial revision for the "${{sectionName}}" section? This will re-evaluate against scholarly standards.`)) return;
      
      btn.disabled = true;
      const label = btn.querySelector('span');
      const originalText = label.textContent;
      label.textContent = " Revising...";

      try {{
        const res = await fetch(`/api/revise/${{topic}}`, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-API-Key': apiKey }},
            body: JSON.stringify({{ section: sectionName }})
        }});
        if (res.ok) window.location.reload();
        else alert("Revision failed.");
      }} catch (err) {{
        alert("Network error.");
        btn.disabled = false;
        label.textContent = originalText;
      }}
    }});
  }});
</script>
</body>
</html>
"""


class ReportGenerator:
    """
    Converts a completed draft + review data into a self-contained HTML report.

    Reads:
      - refined_draft.md  (falls back to draft.md if absent)
      - review.json       (optional — adds quality score cards + suggestions)

    Writes:
      - report.html       (fully self-contained, no external network requests)
    """

    def render_html(
        self,
        draft_path: str,
        review_path: Optional[str],
        topic_slug: str,
    ) -> Optional[str]:
        """Dynamically builds the HTML report string with contextual enrichment."""
        sections = self._parse_draft(draft_path)
        if not sections:
            logger.error("No sections found — cannot render report.")
            return None

        review: Dict[str, Any] = {}
        if review_path and os.path.exists(review_path):
            try:
                with open(review_path, "r", encoding="utf-8") as f:
                    review = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read review.json: {e}")

        # Derive a human-readable title and raw slug
        slug_title = topic_slug.replace("_", " ").title()

        # Build HTML sub-components
        score_strip  = self._build_score_strip(review)
        tab_panels   = self._build_tab_panels(sections, review)
        context_html = self._build_context_strip(topic_slug)

        from datetime import datetime
        date_str = datetime.now().strftime("%d %B %Y, %H:%M")

        html = _HTML_TEMPLATE.format(
            title       = f"{slug_title} &mdash; Research Report",
            subtitle    = slug_title.upper(),
            topic_slug  = topic_slug,
            api_key     = config.APP_API_KEY,
            score_strip = score_strip,
            tab_buttons = "", # Legacy
            tab_panels  = tab_panels,
            context_html = context_html,
            date        = date_str,
        )
        return html

    def _build_context_strip(self, topic_slug: str) -> str:
        """Constructs the 'Key Research Sources & Context' strip from metadata."""
        try:
            metadata_file = os.path.join(config.METADATA_DIR, topic_slug, "papers.json")
            if not os.path.exists(metadata_file):
                return ""

            with open(metadata_file, "r") as f:
                papers_meta = json.load(f)

            from src.core.analysis import PaperAnalyzer
            analyzer = PaperAnalyzer()
            context_data = analyzer.contextualize_papers(papers_meta, {})

            source_cards = ""
            for title, data in context_data.items():
                role_class = data["role"].split()[-1].lower()
                clean_title = title.replace('"', "&quot;")
                pdf_link = data.get("pdf_link", "#")
                # Formatting retrieval metadata
                authors = data.get("authors", [])
                authors_str = " ".join(authors) if authors else "Unknown Authors"
                year_str = data.get("year", "Unknown Year")
                
                url_host = "External Source"
                raw_url = data.get("url", "")
                if "arxiv.org" in raw_url.lower(): url_host = "arXiv Repository"
                elif "semanticscholar.org" in raw_url.lower(): url_host = "Semantic Scholar"
                
                source_cards += (
                    f'<div class="source-card">'
                    f'  <div class="card-header-bar">'
                    f'    <div class="metadata-cluster">'
                    f'       <span class="tag {role_class}">{data["role"]}</span>'
                    f'       <span class="retrieval-source">'
                    f'          <a href="{raw_url}" target="_blank">{url_host}</a><span class="spacer"></span>Published {year_str}'
                    f'       </span>'
                    f'    </div>'
                    f'    <a href="{pdf_link}" target="_blank" class="btn-icon" title="View Paper">'
                    f'      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
                    f'    </a>'
                    f'  </div>'
                    f'  <h4>{clean_title}</h4>'
                    f'  <p class="card-authors">By {authors_str}</p>'
                    f'</div>'
                )

            return (
                '<div class="tab-panel" id="tab-references" role="tabpanel">'
                '  <div class="section-card">'
                '    <div class="section-header-row">'
                '      <h2>References</h2>'
                '    </div>'
                f'   <div class="source-grid" style="margin-top: 1rem;">{source_cards}</div>'
                '  </div>'
                '</div>'
            )
        except Exception as e:
            logger.error(f"Failed to generate context HTML: {e}")
            return ""

    def generate(
        self,
        draft_path: str,
        review_path: Optional[str],
        output_dir: str,
    ) -> Optional[str]:
        """
        Main entry point for file-based generation.

        Args:
            draft_path:  Path to draft.md (or refined_draft.md).
            review_path: Path to review.json, or None if unavailable.
            output_dir:  Directory where report.html will be saved.

        Returns:
            Absolute path to report.html, or None on failure.
        """
        logger.info("Generating HTML report file...")
        
        topic_slug = os.path.basename(output_dir)
        html = self.render_html(draft_path, review_path, topic_slug)
        
        if not html:
            return None

        output_path = os.path.join(output_dir, "report.html")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Report saved to: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to write report.html: {e}")
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_draft(draft_path: str) -> Dict[str, str]:
        """Parses a Markdown draft into {section_name: body_text}."""
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Cannot read draft file: {e}")
            return {}

        sections: Dict[str, str] = {}
        parts = re.split(r"^##\s+(.+)$", content, flags=re.MULTILINE)
        it = iter(parts[1:])
        for heading, body in zip(it, it):
            sections[heading.strip()] = body.strip()
        return sections

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Converts Markdown to HTML, with a plain-text fallback."""
        if _MARKDOWN2_AVAILABLE:
            return markdown2.markdown(
                text,
                extras=["fenced-code-blocks", "tables", "strike", "cuddled-lists"],
            )
        # Minimal fallback: wrap paragraphs in <p> tags
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return "".join(f"<p>{p}</p>" for p in paragraphs)

    @staticmethod
    def _score_class(score: float) -> str:
        if score >= 7:
            return "pass"
        if score >= 4:
            return "warn"
        return "fail"

    def _build_score_strip(self, review: Dict[str, Any]) -> str:
        if not review:
            return ""
        cards = []
        for section, data in review.items():
            score = float(data.get("overall_score", 0))
            cls   = self._score_class(score)
            pct   = min(int(score * 10), 100)
            refined_badge = (
                '<span class="refined-badge">refined</span>'
                if data.get("refined") else ""
            )
            cards.append(f"""
        <div class="score-card">
          <span class="label">{section}</span>
          <span class="value {cls}">{score:.1f}<small style="font-size:1rem;opacity:0.6">/10</small> {refined_badge}</span>
          <div class="bar"><div class="fill fill-{cls}" style="width:{pct}%"></div></div>
        </div>""")
        return f'<div class="summary-strip">{"".join(cards)}</div>'

    def _build_tab_buttons(self, sections: Dict[str, str]) -> str:
        buttons = []
        for i, name in enumerate(sections):
            active = "active" if i == 0 else ""
            tab_id = name.lower().replace(" ", "-")
            buttons.append(
                f'<button class="tab-btn {active}" data-tab="tab-{tab_id}" role="tab">{name}</button>'
            )
        return "\n    ".join(buttons)
    def _build_tab_panels(
        self, sections: Dict[str, str], review: Dict[str, Any]
    ) -> str:
        panels = []
        for i, (name, body) in enumerate(sections.items()):
            if name.lower() == "references":
                continue
            active  = "active" if i == 0 else ""
            tab_id  = "tab-" + name.lower().replace(" ", "-")
            content = self._md_to_html(body)

            # Build hidden extras: suggestions + revise button
            extras_inner = ""

            if name in review:
                sugs = review[name].get("suggestions", [])
                if sugs:
                    items = "".join(f"<li>{s}</li>" for s in sugs)
                    extras_inner += f"""
          <div class="suggestions-box">
            <p class="suggestion-heading">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                AI Insights & Suggestions
            </p>
            <ul>{items}</ul>
          </div>"""

            if name != "References":
                extras_inner += f"""
        <div class="section-controls">
          <button class="btn-revise" data-section="{name}">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
            <span>Critique & Revise</span>
          </button>
        </div>"""

            # Action icon — only shown if there are extras to reveal
            action_btn = ""
            if extras_inner.strip() and name != "References":
                action_btn = """
      <button class="section-action-btn" title="Show AI Options">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
          <path d="M4.93 4.93a10 10 0 0 0 0 14.14"/>
        </svg>
      </button>"""

            extras_block = f'<div class="section-extras">{extras_inner}</div>' if extras_inner.strip() else ""

            panels.append(f"""
  <div class="tab-panel {active}" id="{tab_id}" role="tabpanel">
    <div class="section-card">
      <div class="section-header-row">
        <h2>{name}</h2>
        {action_btn}
      </div>
      {content}
      {extras_block}
    </div>
  </div>""")
        return "\n".join(panels)

    def _render_references(self, body: str) -> str:
        """Renders the References section as a styled <ul> list."""
        if not body or body.startswith("_No paper"):
            return f'<p style="color:var(--muted)">{body}</p>'

        items = []
        for line in body.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Parse numbered entries: "1. Author (Year). *Title*. URL"
            m = re.match(r"^(\d+)\.\s+(.+)$", line)
            if m:
                num, ref = m.group(1), m.group(2)
                # Linkify URLs
                ref = re.sub(
                    r"(https?://\S+)",
                    r'<a href="\1" target="_blank" rel="noopener">\1</a>',
                    ref,
                )
                # Italicise *Title*
                ref = re.sub(r"\*(.+?)\*", r"<em>\1</em>", ref)
                items.append(
                    f'<li class="ref-item"><span class="ref-num">[{num}]</span><span>{ref}</span></li>'
                )
            else:
                items.append(f'<li class="ref-item"><span>{line}</span></li>')

        return f'<ul class="ref-list">{"".join(items)}</ul>'
