import os
import json
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from openai import OpenAI
from src.config import config
from src.utils.logger import logger
from src.core.references import APAFormatter

if TYPE_CHECKING:
    from src.core.retrieval import PaperInfo


class SectionDrafter:
    """
    Generates structured academic section drafts from paper findings.

    Uses GPT to produce five distinct sections:
      - Abstract   : A concise summary of the collective research.
      - Methods    : A synthesized description of methodologies used.
      - Results    : A unified statement of key results and discoveries.
      - Synthesis  : A cross-paper narrative with APA in-text citations.
      - References : APA 7th-edition formatted bibliography.

    Output is written to a single `draft.md` file inside the provided
    topic-specific directory.
    """

    SECTION_SYSTEM_PROMPT = (
        "You are a world-class Professor and educational synthesizer. "
        "Your primary goal is to EXPLAIN the topic to a learner according to the provided papers. "
        "Do not invent facts; rely strictly on the provided findings. Break down complex concepts, define jargon, and teach the material clearly. "
        "Maintain the professional academic structure but use accessible, highly educational prose."
    )

    def __init__(self, model: str = "openai/gpt-4o-mini"):
        self.model = model

    # ------------------------------------------------------------------
    # Public section methods
    # ------------------------------------------------------------------

    def draft_abstract(self, findings: Dict[str, Any]) -> Optional[str]:
        """Generates a high-impact academic Abstract strictly under the 100-word limit."""
        logger.info("Drafting Abstract (100-word limit)...")
        prompt = f"""Write a concise, high-impact **Abstract** from these findings.
CRITICAL CONSTRAINT: You MUST keep the text under 100 words (strict limit).
Cover:
1. Core problem / research question.
2. Primary methodology across papers.
3. Key discoveries or empirical findings.
4. Primary significance.

Findings:
{json.dumps(findings, indent=2)}
"""
        text = self._call_gpt(prompt, section="Abstract")
        if text:
            # Enforce strict word count if needed
            words = text.split()
            if len(words) > 115:
                text = " ".join(words[:100]) + "."
        return text

    def draft_introduction(self, findings: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generates an academic Introduction explaining problem landscape, core concepts, and questions."""
        logger.info("Drafting Introduction section...")
        strategy_context = f"\nResearch Goals & Strategy:\n{json.dumps(plan, indent=2)}" if plan else ""
        prompt = f"""Write an educational, rigorous **Introduction** (2-3 paragraphs) that:
1. Introduces the research field, historical context, and foundational concepts for learners.
2. Formulates the core challenges, problems, and open questions addressed across the literature.
3. Explains the scope of this review and outlines the structure of the paper.

{strategy_context}

Findings from papers:
{json.dumps(findings, indent=2)}
"""
        return self._call_gpt(prompt, section="Introduction")

    def draft_methods(self, findings: Dict[str, Any]) -> Optional[str]:
        """
        Generates a Methods section by synthesizing the methodology
        entries across all papers.

        Args:
            findings: Dict mapping filename → findings dict.

        Returns:
            Draft Methods section text, or None on failure.
        """
        logger.info("Drafting Methods section...")
        prompt = f"""You are given structured findings from multiple research papers.
Write a highly educational **Methods** section (2–3 paragraphs) that:
1. Explains the research approaches and techniques used across the papers as if you are teaching a learner.
2. Clearly defines and explains any complex methodological jargon or algorithms.
3. Highlights how the experiments were designed across the different papers.

Remember: Do not just list methods. Explain *how* they work based strictly on the papers, maintaining a professional but educational tone.

Paper Findings (JSON):
{json.dumps(findings, indent=2)}
"""
        return self._call_gpt(prompt, section="Methods")

    def draft_results(self, findings: Dict[str, Any]) -> Optional[str]:
        """Generates a Results section highlighting discoveries and limitations."""
        logger.info("Drafting Results section...")
        prompt = f"""Write a factual, educational **Results & Discoveries** section (2-3 paragraphs) that:
1. Explains the core factual outcomes and hard data from the selected papers.
2. Breaks down what these discoveries actually mean so a learner can truly understand the topic.
3. Explains the real-world limitations and remaining hurdles mentioned in the papers.
4. NEVER hallucinate data; use only the provided findings.

Findings:
{json.dumps(findings, indent=2)}
"""
        return self._call_gpt(prompt, section="Results")

    def draft_conclusion(self, findings: Dict[str, Any]) -> Optional[str]:
        """Generates a Conclusion section summarizing takeaways, implications, and future directions."""
        logger.info("Drafting Conclusion section...")
        prompt = f"""Write a compelling **Conclusion** section (2 paragraphs) that:
1. Synthesizes the overall state of knowledge and main takeaways established by the reviewed works.
2. Discusses practical implications, open challenges, and promising directions for future research.

Findings:
{json.dumps(findings, indent=2)}
"""
        return self._call_gpt(prompt, section="Conclusion")

    def draft_synthesis(
        self,
        findings: Dict[str, Any],
        papers: Optional[List["PaperInfo"]] = None,
    ) -> Optional[str]:
        """Generates a Synthesis/Discussion section with focus on tensions and strategic outlook."""
        citation_context = ""
        if papers:
            formatter = APAFormatter()
            cite_map = {p.title: formatter.in_text(p) for p in papers if p.title}
            cite_lines = "\n".join(f"  - {title}: {cite}" for title, cite in cite_map.items())
            citation_context = f"\nMandatory in-text citations to use:\n{cite_lines}\n"

        prompt = f"""Write an accessible **Synthesis** section (4 paragraphs):
1. **Integrated Explanation**: Weave the factual findings into a cohesive educational story that thoroughly explains the overarching topic to the learner.
2. **Empirical Tensions**: Explain where the papers disagree or leave gaps, and teach the learner why this happens in this specific research field.
3. **Synergistic Power**: Explain how different methodologies from the papers complement each other.
4. **Learner's Takeaway**: Conclude with a definitive summary of what the learner must understand about this topic.

{citation_context}

Findings:
{json.dumps(findings, indent=2)}
"""
        return self._call_gpt(prompt, section="Synthesis")

    def draft_all(
        self,
        findings: Dict[str, Any],
        drafts_dir: str = config.DRAFTS_DIR,
        papers: Optional[List["PaperInfo"]] = None,
    ) -> Optional[str]:
        """
        Orchestrates all five section drafts and writes them to `draft.md`.

        Sections are generated sequentially:
            Abstract → Methods → Results → Synthesis → References

        Args:
            findings:   Combined findings dict from PaperAnalyzer.
            drafts_dir: Topic-specific directory where draft.md is saved.
            papers:     List of PaperInfo objects for APA citation generation.

        Returns:
            Absolute path to the saved draft.md, or None if all sections failed.
        """
        if not findings:
            logger.warning("No findings provided — cannot generate drafts.")
            return None

        os.makedirs(drafts_dir, exist_ok=True)

        logger.info("Executing parallel section drafting...")
        import concurrent.futures

        # Parallelize API calls to drastically improve throughput
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            future_abstract = executor.submit(self.draft_abstract, findings)
            future_intro = executor.submit(self.draft_introduction, findings)
            future_methods = executor.submit(self.draft_methods, findings)
            future_results = executor.submit(self.draft_results, findings)
            future_conclusion = executor.submit(self.draft_conclusion, findings)
            future_synthesis = executor.submit(self.draft_synthesis, findings, papers)

            abstract = future_abstract.result()
            intro = future_intro.result()
            methods = future_methods.result()
            results = future_results.result()
            conclusion = future_conclusion.result()
            synthesis = future_synthesis.result()

        if not any([abstract, intro, methods, results, conclusion, synthesis]):
            logger.error("All section drafts failed. draft.md not written.")
            return None

        # Build reference list from paper metadata
        ref_block: Optional[str] = None
        if papers:
            formatter = APAFormatter()
            ref_block = formatter.format_reference_list(papers)
            logger.info("APA reference list generated.")

        # Assemble the full markdown document
        lines = ["# Research Paper Draft\n"]

        lines.append("## Abstract\n")
        lines.append(abstract or "_Abstract generation failed._")
        lines.append("\n")

        lines.append("## Introduction\n")
        lines.append(intro or "_Introduction generation failed._")
        lines.append("\n")

        lines.append("## Methods\n")
        lines.append(methods or "_Methods generation failed._")
        lines.append("\n")

        lines.append("## Results\n")
        lines.append(results or "_Results generation failed._")
        lines.append("\n")

        lines.append("## Synthesis\n")
        lines.append(synthesis or "_Synthesis generation failed._")
        lines.append("\n")

        lines.append("## Conclusion\n")
        lines.append(conclusion or "_Conclusion generation failed._")
        lines.append("\n")

        lines.append("## References\n")
        lines.append(ref_block or "_No paper metadata provided for references._")
        lines.append("\n")

        output_path = os.path.join(drafts_dir, "draft.md")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info(f"Draft saved to: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to write draft.md: {e}")
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_gpt(
        self, prompt: str, section: str, max_retries: int = 3, validator=None
    ) -> Optional[str]:
        """Calls the GPT model and returns the response text, with validation and retries."""
        messages = [
            {"role": "system", "content": self.SECTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(max_retries):
            raw_text = ""
            try:
                client = OpenAI(api_key=config.get_next_api_key(), base_url=config.OPENAI_BASE_URL)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=1500,
                )
                raw_text = response.choices[0].message.content or ""
                
                if validator:
                    validator(raw_text)
                else:
                    # Default basic validation for drafts
                    if len(raw_text.strip()) < 50:
                        raise ValueError(f"Draft is too short ({len(raw_text.strip())} chars). Provide full academic paragraphs.")

                logger.info(f"{section} section drafted successfully.")
                return raw_text
                
            except Exception as e:
                logger.warning(f"Error drafting {section} (attempt {attempt+1}/{max_retries}): {e}")
                messages.append({"role": "assistant", "content": raw_text if raw_text else " "})
                messages.append({"role": "user", "content": f"Your output triggered a validation error: {e}\nPlease correct the draft and try again."})
                
        logger.error(f"All GPT retries failed for {section}.")
        return None
