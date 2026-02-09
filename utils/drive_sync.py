from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.settings import LoadSettingsFile
from oauth2client.service_account import ServiceAccountCredentials
import io
import os
import json
import fitz  # PyMuPDF
import logging

import config
from utils.gcp_secrets import get_secret

logger = logging.getLogger("utils.drive_sync")

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

drive = None

def _ensure_drive():
    """
    Initialize Google Drive client with credentials from Secret Manager or environment variable.
    
    Priority order:
    1. Google Cloud Secret Manager (if GOOGLE_PROJECT_ID is configured)
    2. GOOGLE_CREDENTIALS_JSON environment variable (fallback for local development)
    """
    global drive
    if drive is not None:
        return drive

    gauth = GoogleAuth()
    
    # Try Secret Manager first (if GOOGLE_PROJECT_ID is configured)
    secret_name = config.GOOGLE_SECRET_NAME
    credentials_json = None
    
    if config.GOOGLE_PROJECT_ID:
        logger.info(f"🔐 Attempting to load Google credentials from Secret Manager (secret: {secret_name})")
        credentials_json = get_secret(secret_name, config.GOOGLE_PROJECT_ID)
        if credentials_json:
            logger.info("✅ Loaded Google credentials from Secret Manager")
    
    # Fallback to environment variable if Secret Manager didn't provide credentials
    if not credentials_json:
        credentials_json = config.GOOGLE_CREDENTIALS_JSON
        if credentials_json:
            logger.info("🔐 Loading Google Service Account credentials from environment variable")
        else:
            logger.warning("GOOGLE_CREDENTIALS_JSON not set and Secret Manager unavailable; Drive features disabled")
            return None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            json.loads(credentials_json),
            SCOPES
        )
        gauth.credentials = creds
        drive = GoogleDrive(gauth)
        logger.info("✅ Google Drive service account authentication successful")
        return drive
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Google credentials JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Google Drive client: {e}", exc_info=True)
        return None


def _sanitize_drive_query_keyword(keyword: str) -> str:
    """
    Sanitizes a keyword for use in Google Drive API query strings.
    
    Escapes single quotes to prevent query injection and manipulation.
    Replaces single quotes with escaped single quotes or removes them.
    
    Args:
        keyword: User-provided keyword that may contain special characters
        
    Returns:
        Sanitized keyword safe for use in Drive API queries
    """
    if not keyword:
        return ""
    # Escape single quotes by replacing with escaped version
    # Google Drive API uses single quotes for string literals
    return keyword.replace("'", "\\'").replace('"', '\\"')


def fetch_pdf_text_by_name(filename_keyword: str) -> str:
    """
    Zoek een PDF in Google Drive op basis van een zoekwoord in de bestandsnaam,
    download hem tijdelijk en haal de tekstinhoud eruit.
    
    Args:
        filename_keyword: Search keyword (should be sanitized before calling)
    """
    gd = _ensure_drive()
    if gd is None:
        return "[Drive not configured: set GOOGLE_CREDENTIALS_JSON]"

    # Sanitize the keyword to prevent query injection
    sanitized_keyword = _sanitize_drive_query_keyword(filename_keyword)
    query = f"title contains '{sanitized_keyword}' and mimeType = 'application/pdf' and trashed = false"
    logger.info(f"Searching Google Drive for: {filename_keyword}")
    file_list = gd.ListFile({'q': query}).GetList()

    if not file_list:
        logger.warning(f"No matching PDF found for keyword: {filename_keyword}")
        return "[No matching file found in Drive]"

    file = file_list[0]  # neem de eerste match
    logger.info(f"Found PDF in Drive: {file['title']}")
    downloaded = file.GetContentIOBuffer()
    pdf_text = extract_text_from_pdf(downloaded)
    return pdf_text


def extract_text_from_pdf(file_buffer: io.BytesIO) -> str:
    """
    Extracts text from a PDF file buffer using PyMuPDF
    """
    text = ""
    try:
        with fitz.open(stream=file_buffer, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return f"[Error extracting PDF text: {e}]"
