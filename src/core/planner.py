import json
from typing import Dict, Any, List, Optional
from openai import OpenAI
from src.config import config
from src.utils.logger import logger

class ResearchPlanner:
    """
    Analyzes a research topic and generates a structured research strategy.
    This is the first brain in the agentic workflow.
    """

    def __init__(self, model: str = "openai/gpt-4o-mini"):
        self.model = model

    def generate_plan(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Generates a research plan including optimized queries and structural goals.
        """
        prompt = f"""
        You are an Educational Strategy Agent. Your goal is to take a research topic and create a plan to teach it deeply to a learner.
        
        Topic: "{topic}"
        
        Generate a JSON object with the following structure:
        {{
          "refined_topic": "A clear, focused educational name for the topic",
          "optimized_queries": ["list of 3-5 specific ArXiv search strings to find foundational papers"],
          "key_questions": ["3-5 core questions a student must understand about this topic"],
          "structural_goal": "What the final educational report should accomplish (e.g., 'A clear explanation of...')",
          "suggested_sections": ["Introduction", "Core Concepts", "Recent Breakthroughs", "Limitations"]
        }}
        
        Constraints:
        - Output MUST be valid JSON.
        - Queries should be optimized for technical accuracy.
        - All content must be in English.
        """

        try:
            logger.info(f"[Planner] Generating strategy for topic: '{topic}'")
            client = OpenAI(api_key=config.get_next_api_key(), base_url=config.OPENAI_BASE_URL)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a world-class Professor and educational planner. Provide structured JSON output."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            plan = json.loads(response.choices[0].message.content)
            logger.info(f"[Planner] Strategy generated successfully.")
            return plan
        except Exception as e:
            logger.error(f"[Planner] Error generating research plan: {e}")
            return None
