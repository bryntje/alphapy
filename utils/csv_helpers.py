"""
CSV export utilities for consistent file generation and Discord file handling.
"""
import csv
import io
import os
import discord
from typing import List, Dict, Any, Optional


def create_csv_buffer(rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> io.StringIO:
    """Create a CSV buffer from database rows."""
    if not fieldnames and rows:
        fieldnames = list(rows[0].keys())

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return buf


def create_discord_file_from_buffer(buf: io.StringIO, filename: str) -> discord.File:
    """Create a Discord file from a CSV buffer."""
    buf.seek(0)
    content = buf.getvalue()
    buf.close()

    # Create bytes buffer for Discord
    bytes_buf = io.BytesIO(content.encode('utf-8'))
    return discord.File(bytes_buf, filename=filename)


def create_temp_csv_file(rows: List[Dict[str, Any]], filename: str, fieldnames: Optional[List[str]] = None) -> str:
    """Create a temporary CSV file (legacy method - prefer buffer method)."""
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        if not fieldnames and rows:
            fieldnames = list(rows[0].keys())
        csv_writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        csv_writer.writeheader()
        csv_writer.writerows(rows)
    return filename


def cleanup_temp_file(filename: str) -> None:
    """Clean up temporary CSV file."""
    try:
        if os.path.exists(filename):
            os.remove(filename)
    except Exception:
        pass  # Ignore cleanup errors