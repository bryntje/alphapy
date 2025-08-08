from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.settings import LoadSettingsFile
from oauth2client.service_account import ServiceAccountCredentials
import io
import os
import json
import fitz  # PyMuPDF
import logging


logger = logging.getLogger("utils.drive_sync")

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

drive = None

def _ensure_drive():
    global drive
    if drive is not None:
        return drive

    gauth = GoogleAuth()
    creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")

    if not creds_env:
        logger.warning("GOOGLE_CREDENTIALS_JSON not set; Drive features disabled")
        return None

    logger.info("🔐 Loading Google Service Account credentials from env")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(creds_env),
        SCOPES
    )

    gauth.credentials = creds
    drive = GoogleDrive(gauth)
    logger.info("✅ Google Drive service account authentication successful")
    return drive


def fetch_pdf_text_by_name(filename_keyword: str) -> str:
    """
    Zoek een PDF in Google Drive op basis van een zoekwoord in de bestandsnaam,
    download hem tijdelijk en haal de tekstinhoud eruit.
    """
    gd = _ensure_drive()
    if gd is None:
        return "[Drive not configured: set GOOGLE_CREDENTIALS_JSON]"

    query = f"title contains '{filename_keyword}' and mimeType = 'application/pdf' and trashed = false"
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
