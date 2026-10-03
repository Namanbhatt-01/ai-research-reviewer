import os
import argparse
import sys
import time

# Ensure src is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.reports.report_generator import ReportGenerator
from src.config import config
from src.utils.logger import logger

def process_topic(generator: ReportGenerator, topic_slug: str) -> bool:
    """Helper to generate a report for a specific topic slug."""
    topic_dir = os.path.join(config.DRAFTS_DIR, topic_slug)
    
    # Priority: refined_draft.md > draft.md
    refined_path = os.path.join(topic_dir, "refined_draft.md")
    draft_path = os.path.join(topic_dir, "draft.md")
    
    final_draft = refined_path if os.path.exists(refined_path) else draft_path
    review_path = os.path.join(topic_dir, "review.json")
    
    if not os.path.exists(final_draft):
        logger.warning(f"No draft found for {topic_slug} (checked {os.path.basename(final_draft)})")
        return False

    try:
        marker = "[REFINED]" if "refined" in final_draft else "[INITIAL]"
        print(f"  + Generating {marker} report for: {topic_slug}")
        
        # Generator handles the output_dir logic internally or via the 3rd arg
        generator.generate(final_draft, review_path, topic_dir)
        return True
    except Exception as e:
        logger.error(f"Failed to generate report for {topic_slug}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="🚀 AI Research Report Hub - CLI Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python scripts/report_tool.py --topic quantum_computing\n  python scripts/report_tool.py --all"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--topic", help="Topic slug to generate report for")
    group.add_argument("--all", action="store_true", help="Generate reports for all available drafts")
    
    args = parser.parse_args()
    generator = ReportGenerator()
    
    start_time = time.time()

    if args.all:
        if not os.path.exists(config.DRAFTS_DIR):
            print(f" Error: Drafts directory not found at {config.DRAFTS_DIR}")
            sys.exit(1)
            
        topics = [d for d in os.listdir(config.DRAFTS_DIR) 
                 if os.path.isdir(os.path.join(config.DRAFTS_DIR, d))]
        
        if not topics:
            print("ℹ️ No topics found in drafts directory.")
            return

        print(f"📋 Found {len(topics)} topics. Starting batch generation...")
        success_count = 0
        for topic in topics:
            if process_topic(generator, topic):
                success_count += 1
        
        elapsed = time.time() - start_time
        print(f"\n✨ Batch complete! Success: {success_count}/{len(topics)}")
        print(f"⏱️  Time elapsed: {elapsed:.2f}s")
        
    elif args.topic:
        if process_topic(generator, args.topic):
            print(f" Success: Report for '{args.topic}' is ready.")
        else:
            print(f" Failed: Could not generate report for '{args.topic}'. Check logs for details.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user.")
        sys.exit(0)
