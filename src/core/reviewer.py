import os
import json
import re
from typing import Dict, Any, List, Optional

from openai import OpenAI
from src.config import config
from src.utils.logger import logger


# Sections present in draft.md that will be reviewed
REVIEWABLE_SECTIONS = ["Abstract", "Introduction", "Methods", "Results", "Conclusion", "Synthesis"]


class DraftReviewer:
    """
    Reviews and refines GPT-generated draft sections.

    Workflow per section:
      1. evaluate_section()  → structured quality scores (0–10) + feedback
      2. suggest_revisions() → concrete, actionable revision suggestions
      3. refine_section()    → GPT rewrites the section using the feedback
                               (only triggered when overall score < REVIEW_PASSING_SCORE)

    Outputs written to the topic-specific drafts directory:
      - review.json       : scores and suggestions for every section
      - refined_draft.md  : sections rewritten where score was below threshold
    """

    SYSTEM_REVIEWER = (
        "You are an expert Educational Reviewer and academic editor. "
        "Evaluate scientific writing for factual accuracy, extreme clarity, and educational value for a learner. "
        "Do not settle for dense jargon; demand simple explanations and clear definitions of complex problems."
    )
    SYSTEM_WRITER = (
        "You are a world-class Professor and Academic Editor. "
        "Rewrite scientific prose to be more accessible, educational, and factual. "
        "Ensure complex concepts are broken down and that the text strictly avoids hallucinating facts. "
        "Write full, professional paragraphs only."
    )

    def __init__(self, model: str = "openai/gpt-4o-mini"):
        self.model = model
        self.passing_score: int = config.REVIEW_PASSING_SCORE

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def evaluate_section(self, name: str, text: str) -> Dict[str, Any]:
        """
        Evaluates a single draft section using deterministic rule-based heuristics.
        Replaces the previous expensive GPT call to compute scores.

        Returns a dict like:
        {
          "clarity":        {"score": 8, "feedback": "..."},
          "academic_rigor": {"score": 6, "feedback": "..."},
          "completeness":   {"score": 7, "feedback": "..."},
          "citation_usage": {"score": 9, "feedback": "..."},
          "overall":        8.0
        }
        """
        logger.info(f"Evaluating '{name}' section with heuristics...")
        words = text.split()
        word_count = len(words)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        sentence_count = max(len(sentences), 1)
        avg_sentence_length = word_count / sentence_count

        # 1. Clarity (Penalty for extremely long or short sentences)
        clarity_score = 10
        if avg_sentence_length > 30:
            clarity_score = max(0, 10 - int((avg_sentence_length - 30) // 5))
            clarity_fb = f"Sentences are too long on average ({avg_sentence_length:.1f} words)."
        elif avg_sentence_length < 10:
            clarity_score = 6
            clarity_fb = "Sentences are too short and choppy."
        else:
            clarity_fb = "Sentence length is optimal and readable."

        # 2. Completeness (Penalty for sections that are too short based on name)
        completeness_score = 10
        completeness_fb = "Section appears comprehensive."
        min_words = {"Abstract": 50, "Introduction": 120, "Methods": 150, "Results": 150, "Synthesis": 180, "Conclusion": 100}.get(name, 100)
        if word_count < min_words:
            completeness_score = max(1, int(10 * (word_count / min_words)))
            completeness_fb = f"Section is too brief ({word_count} words). Expected at least {min_words}."

        # 3. Citation Usage (Regex count for (Author, Year) or (Author et al., Year))
        citation_matches = len(re.findall(r'\([A-Za-z\s]+(?:et al\.)?,\s\d{4}\)', text))
        if name in ["Synthesis", "Methods"]:
            if citation_matches == 0:
                citation_score = 2
                citation_fb = "No in-text citations found where expected."
            elif citation_matches < 3:
                citation_score = 6
                citation_fb = f"Sparse citation density ({citation_matches} found)."
            else:
                citation_score = 10
                citation_fb = f"Good use of citations ({citation_matches} identified)."
        else:
            # Abstract and Results might not strictly need citations in this context
            citation_score = 10
            citation_fb = "Citations are adequate or not strictly required here."

        # 4. Insight Depth (Penalty for lack of critical/comparison words)
        critical_indicators = ["however", "contrast", "limitation", "bottleneck", "tension", "disagree", "critique", "novelty", "gap"]
        indicator_count = sum(1 for w in words if w.lower() in critical_indicators)
        
        insight_score = 10
        if indicator_count == 0:
            insight_score = 4
            insight_fb = "Section is purely descriptive. Needs more critical analysis of tensions or gaps."
        elif indicator_count < 3:
            insight_score = 7
            insight_fb = "Some critical perspective, but could be deeper."
        else:
            insight_fb = "Strong critical depth and analytical perspective."

        # 5. Academic Rigor
        casual_words = ["good", "bad", "huge", "very", "really", "stuff", "things"]
        casual_count = sum(1 for w in words if w.lower() in casual_words)
        academic_rigor_score = max(1, 10 - casual_count)
        academic_rigor_fb = "Tone appears objective." if casual_count == 0 else f"Avoid informal terms ({casual_count} found)."

        raw = {
            "clarity": {"score": clarity_score, "feedback": clarity_fb},
            "insight_depth": {"score": insight_score, "feedback": insight_fb},
            "completeness": {"score": completeness_score, "feedback": completeness_fb},
            "citation_usage": {"score": citation_score, "feedback": citation_fb},
            "academic_rigor": {"score": academic_rigor_score, "feedback": academic_rigor_fb}
        }
        
        scores = [raw[d]["score"] for d in ["clarity", "insight_depth", "completeness"]]
        raw["overall"] = round(sum(scores) / len(scores), 1) if scores else 0.0
        
        return raw

    def suggest_revisions(
        self, name: str, text: str, evaluation: Dict[str, Any]
    ) -> List[str]:
        """
        Generates a list of specific, actionable revision suggestions for a section.
        """
        logger.info(f"Generating revision suggestions for '{name}'...")
        eval_summary = json.dumps(
            {k: v for k, v in evaluation.items() if k != "overall"}, indent=2
        )
        prompt = f"""You evaluated the **{name}** section of an academic paper with these scores:
{eval_summary}

Based on the feedback above, list 3–5 specific, actionable revision suggestions.
You MUST return ONLY a JSON object with a 'suggestions' key that maps to an array of strings.
Example: {{"suggestions": ["Suggestion 1", "Suggestion 2"]}}

Section text:
\"\"\"
{text[:4000]}
\"\"\"
"""
        def validate_schema(parsed_json):
            if not isinstance(parsed_json, dict) or "suggestions" not in parsed_json:
                raise ValueError("Payload must be a JSON object containing a 'suggestions' key.")
            if not isinstance(parsed_json["suggestions"], list):
                raise ValueError("'suggestions' must be a list of strings.")

        raw = self._call_gpt(prompt, system=self.SYSTEM_REVIEWER, as_json=True, validator=validate_schema)
        
        if raw and "suggestions" in raw and isinstance(raw["suggestions"], list):
            return [str(s) for s in raw["suggestions"]]
        
        # Fallback Strategy if all retries exhausted
        logger.warning(f"Exhausted retries for {name} suggestions. Using empty fallback.")
        return []

    def refine_section(
        self, name: str, text: str, suggestions: List[str], context: Optional[str] = None
    ) -> Optional[str]:
        """
        Rewrites *text* guided by *suggestions* and optional *context*, producing an improved section.

        Args:
            name:        Section name for context.
            text:        Original section text to refine.
            suggestions: Revision suggestions from suggest_revisions().
            context:     Verified empirical paper findings or metadata to ground the prose.

        Returns:
            Refined section text, or None on failure.
        """
        logger.info(f"Refining '{name}' section...")
        bullet_suggestions = "\n".join(f"- {s}" for s in suggestions)
        context_block = f"\nEmpirical Context & Verified Research Findings:\n{context}\n" if context else ""
        prompt = f"""Rewrite the **{name}** section of an academic systematic review to address the following editorial critique:
{bullet_suggestions}
{context_block}
Requirements:
1. Write in fluent, authoritative, publication-quality academic English.
2. Ground all statements in concrete technical specifics (exact model names, architectural mechanisms, benchmark metrics, datasets, and author attributions). Avoid vague generic filler like 'advanced algorithmic architectures'.
3. Preserve all verified empirical numbers, equations, and in-text citations.
4. If this is the 'Abstract' section, keep it concise and under 120 words.

Original section text:
\"\"\"
{text[:6000]}
\"\"\"
"""
        return self._call_gpt(prompt, system=self.SYSTEM_WRITER, as_json=False)

    def _process_single_section(self, section_name: str, section_text: str) -> Dict[str, Any]:
        """Worker function for parallelizing section review."""
        evaluation = self.evaluate_section(section_name, section_text)
        suggestions = self.suggest_revisions(section_name, section_text, evaluation)
        overall = evaluation.get("overall", 0.0)

        result = {
            "name": section_name,
            "text": section_text,
            "evaluation": evaluation,
            "suggestions": suggestions,
            "overall_score": overall,
            "refined": False,
            "refined_text": None,
        }

        if overall < self.passing_score:
            logger.info(f"'{section_name}' scored {overall} < {self.passing_score} — auto-refining.")
            refined = self.refine_section(section_name, section_text, suggestions)
            if refined:
                result["refined_text"] = refined
                result["refined"] = True
        else:
            logger.info(f"'{section_name}' passed review with score {overall}.")
            
        return result

    def review_draft(
        self,
        draft_path: str,
        drafts_dir: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Full review-and-refinement cycle for a complete draft.md file.

        Steps:
          1. Parse draft.md into sections.
          2. Concurrently evaluate + suggest revisions for every reviewable section using ThreadPoolExecutor.
          3. Auto-refine sections whose overall score < config.REVIEW_PASSING_SCORE.
          4. Save review.json (scores + suggestions) and refined_draft.md.

        Args:
            draft_path: Absolute path to the draft.md file.
            drafts_dir: Directory where review outputs will be saved.

        Returns:
            Dict with keys: "scores" (per-section), "refined_sections" (list of names).
        """
        logger.info(f"Starting parallel review cycle for: {draft_path}")

        sections = self._parse_draft(draft_path)
        if not sections:
            logger.error("Could not parse any sections from draft.md.")
            return None

        review_data: Dict[str, Any] = {}
        refined_sections: Dict[str, str] = {}
        
        import concurrent.futures
        
        target_sections = {k: v for k, v in sections.items() if k in REVIEWABLE_SECTIONS}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_name = {
                executor.submit(self._process_single_section, name, text): name
                for name, text in target_sections.items()
            }
            for future in concurrent.futures.as_completed(future_to_name):
                res = future.result()
                name = res["name"]
                review_data[name] = {
                    "evaluation": res["evaluation"],
                    "suggestions": res["suggestions"],
                    "overall_score": res["overall_score"],
                    "refined": res["refined"]
                }
                if res["refined"]:
                    refined_sections[name] = res["refined_text"]

        # Save review.json
        review_path = os.path.join(drafts_dir, "review.json")
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump(review_data, f, indent=4)
        logger.info(f"Review data saved to: {review_path}")

        # Build and save refined_draft.md
        self._write_refined_draft(
            sections=sections,
            refined_sections=refined_sections,
            drafts_dir=drafts_dir,
        )

        return {
            "scores": {k: v["overall_score"] for k, v in review_data.items()},
            "refined_sections": [k for k, v in review_data.items() if v["refined"]],
            "review_path": review_path,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_draft(self, draft_path: str) -> Dict[str, str]:
        """
        Parses a Markdown draft into {section_name: section_text} dict.
        Splits on level-2 headings (## Heading).
        """
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read draft file: {e}")
            return {}

        sections: Dict[str, str] = {}
        # Split on ## headings
        parts = re.split(r"^##\s+(.+)$", content, flags=re.MULTILINE)
        # parts = [preamble, heading1, body1, heading2, body2, ...]
        it = iter(parts[1:])  # skip preamble
        for heading, body in zip(it, it):
            sections[heading.strip()] = body.strip()

        return sections

    def _write_refined_draft(
        self,
        sections: Dict[str, str],
        refined_sections: Dict[str, str],
        drafts_dir: str,
    ) -> None:
        """Writes refined_draft.md, replacing refined sections in-place."""
        lines = ["# Research Paper Draft (Refined)\n"]
        for name, text in sections.items():
            lines.append(f"## {name}\n")
            lines.append(refined_sections.get(name, text))
            lines.append("\n")

        output_path = os.path.join(drafts_dir, "refined_draft.md")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info(f"Refined draft saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to write refined_draft.md: {e}")

    def _call_gpt(
        self, prompt: str, system: str, as_json: bool, max_retries: int = 3, validator=None
    ):
        """Calls GPT with an optional JSON response format, implementing retry/auto-correction logic."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1500,
        }
        if as_json:
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(max_retries):
            raw_text = ""
            try:
                client = OpenAI(api_key=config.get_next_api_key(), base_url=config.OPENAI_BASE_URL)
                response = client.chat.completions.create(messages=messages, **kwargs)
                raw_text = response.choices[0].message.content or ""
                
                if as_json:
                    parsed = json.loads(raw_text)
                    if validator:
                        validator(parsed)
                    return parsed
                else:
                    if validator:
                        validator(raw_text)
                    return raw_text
                    
            except Exception as e:
                logger.warning(f"GPT call validation failed (attempt {attempt+1}/{max_retries}): {e}")
                if "401" in str(e) or "expired" in str(e).lower() or "authentication" in str(e).lower():
                    logger.warning("API key expired or unauthorized. Skipping self-correction retries.")
                    break
                # Feed the failure back into the GPT context so it can self-correct!
                messages.append({"role": "assistant", "content": raw_text if raw_text else "{}"})
                messages.append({"role": "user", "content": f"Your output triggered a validation error: {e}\nPlease correct the formatting and try again."})

        logger.error("All GPT self-correction retries failed.")
        return None
