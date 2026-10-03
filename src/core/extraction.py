import os
import pymupdf4llm
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from src.config import config
from src.utils.logger import logger


class PDFExtractor:
    """Encapsulates PDF text extraction logic using PyMuPDF4LLM."""

    def __init__(self, output_folder: str = config.PROCESSED_TEXT_DIR):
        self.output_folder = output_folder

    def extract_to_markdown(
        self, pdf_path: str, output_folder: Optional[str] = None
    ) -> Optional[str]:
        """
        Extracts content from a PDF and saves it as a Markdown file.

        Args:
            pdf_path: Path to the source PDF file.
            output_folder: Where to write the .md file. Overrides self.output_folder
                           when provided (e.g. a topic-specific subfolder).

        Returns:
            Path to the extracted Markdown file, or None on failure.
        """
        dest = output_folder or self.output_folder
        os.makedirs(dest, exist_ok=True)

        base_name = os.path.basename(pdf_path)
        file_name_no_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(dest, f"{file_name_no_ext}.md")

        try:
            logger.info(f"Extracting text from: {base_name}")
            md_text = pymupdf4llm.to_markdown(pdf_path)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md_text)

            logger.info(f"Extracted text saved to: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return None

    def process_directory(
        self,
        input_folder: str = config.RAW_PDF_DIR,
        output_folder: Optional[str] = None,
    ) -> List[str]:
        """
        Processes all PDFs in *input_folder* and writes extracted Markdown files.

        Args:
            input_folder: Directory containing the source PDF files.
            output_folder: Where to write output .md files. When provided
                           (topic-specific path), overrides self.output_folder.

        Returns:
            List of paths to the successfully extracted Markdown files.
        """
        if not os.path.exists(input_folder):
            logger.error(f"Input folder does not exist: {input_folder}")
            return []

        pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith(".pdf")]
        processed_paths: List[str] = []

        logger.info(f"Starting parallel extraction for {len(pdf_files)} files...")
        
        def _extract(pdf_file):
            pdf_path = os.path.join(input_folder, pdf_file)
            return self.extract_to_markdown(pdf_path, output_folder=output_folder)

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(_extract, pdf_files))
            processed_paths = [r for r in results if r]

        logger.info(f"Finished processing directory. Total files extracted: {len(processed_paths)}")
        return processed_paths
