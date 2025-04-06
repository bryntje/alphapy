import io
import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import fitz  # PyMuPDF

CREDENTIALS_PATH = "credentials/credentials.json"

# Authorize PyDrive
_gauth = GoogleAuth()
_gauth.LoadClientConfigFile(CREDENTIALS_PATH)
_gauth.LocalWebserverAuth()
drive = GoogleDrive(_gauth)

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
