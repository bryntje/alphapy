import io
import os
import json
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import fitz  # PyMuPDF

gauth = GoogleAuth()

# Load credentials from environment or fallback to file
creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if creds_env:
    gauth.LoadClientConfig(json.loads(creds_env))
else:
    gauth.LoadClientConfigFile("credentials/credentials.json")

gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

def fetch_pdf_text_by_name(filename_keyword: str) -> str:
    """
    Zoek een PDF in Google Drive op basis van een zoekwoord in de bestandsnaam,
    download hem tijdelijk en haal de tekstinhoud eruit.
    """
    query = f"title contains '{filename_keyword}' and mimeType = 'application/pdf' and trashed = false"
    file_list = drive.ListFile({'q': query}).GetList()

    if not file_list:
        return "[No matching file found in Drive]"

    file = file_list[0]  # neem de eerste match
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
        return f"[Error extracting PDF text: {e}]"
