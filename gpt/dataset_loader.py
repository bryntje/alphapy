import os
import logging
import asyncio

from utils.drive_sync import fetch_pdf_text_by_name

logger = logging.getLogger(__name__)

BASE_PATH = "data/prompts"

# Error prefixes returned by fetch_pdf_text_by_name when Drive is unavailable or file not found
DRIVE_ERROR_PREFIXES = ("[Drive not configured", "[No matching", "[Error")


def _sanitize_topic_for_drive(topic: str) -> str:
    """
    Sanitizes a topic string for use in Google Drive queries.
    
    Removes or escapes characters that could break Drive API queries.
    This is a basic sanitization - the actual query sanitization happens
    in utils.drive_sync._sanitize_drive_query_keyword().
    
    Args:
        topic: User-provided topic string
        
    Returns:
        Sanitized topic string safe for Drive queries
    """
    if not topic:
        return ""
    # Remove control characters and limit length
    import re
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", topic)
    # Limit length to prevent extremely long queries
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized.strip()


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
        # Sanitize topic before passing to Drive API to prevent query injection
        sanitized_topic = _sanitize_topic_for_drive(topic)
        if not sanitized_topic:
            logger.debug(f"Topic sanitization resulted in empty string, skipping Drive search")
            return ""
        
        # Run synchronous Drive API call in thread pool to avoid blocking event loop
        drive_content = await asyncio.to_thread(fetch_pdf_text_by_name, sanitized_topic)
        if drive_content and not drive_content.startswith(DRIVE_ERROR_PREFIXES):
            logger.info(f"✅ Loaded context from Google Drive PDF for topic: {topic}")
            return drive_content
        else:
            logger.debug(f"No matching PDF found in Drive for: {topic}")
    except Exception as e:
        logger.debug(f"Error fetching from Drive for {topic}: {e}")
    
    # No context found
    return ""
