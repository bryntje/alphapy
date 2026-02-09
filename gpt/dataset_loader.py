import os
import logging

from utils.drive_sync import fetch_pdf_text_by_name

logger = logging.getLogger(__name__)

BASE_PATH = "data/prompts"

# Error prefixes returned by fetch_pdf_text_by_name when Drive is unavailable or file not found
DRIVE_ERROR_PREFIXES = ("[Drive not configured", "[No matching", "[Error")

async def load_topic_context(topic: str) -> str:
    """
    Laadt contextuele uitleg op basis van een topic keyword (zoals 'rsi')
    uit een .md of .txt bestand in /data/prompts/, of uit Google Drive als PDF.
    
    Priority:
    1. Local .md file in data/prompts/
    2. Google Drive PDF (if Drive is configured)
    3. Empty string if nothing found
    """
    # Try local file first
    filename = topic.lower().replace(" ", "_") + ".md"
    file_path = os.path.join(BASE_PATH, filename)

    if os.path.exists(file_path):
        logger.debug(f"Loading context from local file: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    
    # Try Google Drive PDF as fallback
    try:
        logger.debug(f"Local file not found, trying Google Drive for: {topic}")
        drive_content = fetch_pdf_text_by_name(topic)
        if drive_content and not drive_content.startswith(DRIVE_ERROR_PREFIXES):
            logger.info(f"✅ Loaded context from Google Drive PDF for topic: {topic}")
            return drive_content
        else:
            logger.debug(f"No matching PDF found in Drive for: {topic}")
    except Exception as e:
        logger.debug(f"Error fetching from Drive for {topic}: {e}")
    
    # No context found
    return ""
