"""
Embed Parser Utilities

Pure date/time parsing and text-formatting helpers extracted from EmbedReminderWatcher.
No Discord objects, no DB access, no async — these functions are fully testable in isolation.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from utils.logger import logger
from utils.parsers import parse_days_string
from utils.timezone import BRUSSELS_TZ


def extract_datetime_from_text(text: str) -> Optional[datetime]:
    """Parse a free-text date/time, trying numeric and natural language formats."""
    date_match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
    time_match = re.search(r"(\d{1,2}[:.]\d{2})", text)
    current_year = datetime.now(BRUSSELS_TZ).year

    if date_match and time_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = date_match.group(3)
        if year:
            year = int(year) if len(year) == 4 else 2000 + int(year)
        else:
            year = current_year
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day}/{month}/{year} {time_str}", "%d/%m/%Y %H:%M")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BRUSSELS_TZ)
            return dt
        except Exception as e:
            logger.warning(f"⛔️ Date parse failed: {e}")

    date_match = re.search(r"(\d{1,2})(st|nd|rd|th)?\s+([A-Z][a-z]+)", text)
    if date_match and time_match:
        day = int(date_match.group(1))
        month_str = date_match.group(3)
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day} {month_str} {current_year} {time_str}", "%d %B %Y %H:%M")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BRUSSELS_TZ)
            return dt
        except Exception as e:
            logger.warning(f"⛔️ Date parse failed: {e}")
    return None


def extract_fields_from_lines(
    lines: List[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract date, time, location, and days fields from structured embed lines."""
    date_line = time_line = location_line = days_line = None
    for line in lines:
        lower = line.lower()
        if "date:" in lower:
            date_line = line.split(":", 1)[1].strip()
        elif "time:" in lower:
            time_line = line.split(":", 1)[1].strip()
        elif "location:" in lower or "locatie:" in lower:
            location_line = line.split(":", 1)[1].strip()
        elif "days:" in lower:
            days_line = line.split(":", 1)[1].strip()
    return date_line, time_line, location_line, days_line


def parse_datetime(
    date_line: Optional[str], time_line: Optional[str]
) -> Tuple[Optional[datetime], Optional[object]]:
    """Parse a date+time from structured embed fields into a timezone-aware datetime."""
    if not time_line:
        logger.warning(f"❌ No valid time found in line: {time_line}")
        return None, None

    time_match = re.search(r"^.*?(\d{1,2})[:.](\d{2})(?:\s*(CET|CEST))?.*$", time_line)
    if not time_match:
        return None, None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    _timezone_str = time_match.group(3) or "CET"

    tz = BRUSSELS_TZ

    if date_line:
        date_line = date_line.strip()
        numeric = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", date_line)
        if numeric:
            day = int(numeric.group(1))
            month = int(numeric.group(2))
            year = numeric.group(3)
            if year:
                year = int(year) if len(year) == 4 else 2000 + int(year)
            else:
                year = datetime.now(BRUSSELS_TZ).year
        else:
            date_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?", date_line)
            if not date_match:
                alt_match = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", date_line)
                if not alt_match:
                    return None, None
                month_str, day, year = alt_match.groups()
            else:
                day, month_str, year = date_match.groups()
            day = int(day)
            year = int(year) if year else datetime.now(BRUSSELS_TZ).year
            try:
                month = datetime.strptime(month_str[:3], "%b").month
            except ValueError:
                month = datetime.strptime(month_str, "%B").month
        dt = datetime(year, month, day, hour, minute, tzinfo=tz)
    else:
        now = datetime.now(BRUSSELS_TZ)
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return dt, tz


def infer_date_from_time_line(time_line: str) -> Optional[str]:
    """Try to extract a date string embedded in a time-line value."""
    numeric = re.search(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", time_line)
    if numeric:
        return numeric.group(1)

    month_day = re.search(
        r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:[,\s]+(\d{4}))?",
        time_line,
    )
    if month_day:
        month, day, year = month_day.groups()
        parts = [day, month]
        if year:
            parts.append(year)
        return " ".join(parts)

    day_month = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:[,\s]+(\d{4}))?",
        time_line,
    )
    if day_month:
        day, month, year = day_month.groups()
        parts = [day, month]
        if year:
            parts.append(year)
        return " ".join(parts)

    return None


def parse_relative_date(text: str) -> Optional[str]:
    """Parse relative dates like 'This Wednesday', 'Next Friday', 'Tomorrow' etc."""
    now = datetime.now(BRUSSELS_TZ)
    text_lower = text.lower()

    day_map = {
        "monday": 0, "maandag": 0, "mon": 0, "ma": 0,
        "tuesday": 1, "dinsdag": 1, "tue": 1, "di": 1,
        "wednesday": 2, "woensdag": 2, "wed": 2, "woe": 2, "wo": 2,
        "thursday": 3, "donderdag": 3, "thu": 3, "do": 3,
        "friday": 4, "vrijdag": 4, "fri": 4, "vr": 4,
        "saturday": 5, "zaterdag": 5, "sat": 5, "za": 5,
        "sunday": 6, "zondag": 6, "sun": 6, "zo": 6,
    }

    this_match = re.search(
        r"\bthis\s+(?:coming\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r"|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag"
        r"|mon|tue|wed|thu|fri|sat|sun|ma|di|woe?|do|vr|za|zo)\b",
        text_lower,
    )
    if this_match:
        day_name = this_match.group(1)
        if day_name in day_map:
            target_weekday = day_map[day_name]
            current_weekday = now.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
            return target_date.strftime("%d/%m/%Y")

    next_match = re.search(
        r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r"|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag"
        r"|mon|tue|wed|thu|fri|sat|sun|ma|di|woe?|do|vr|za|zo)\b",
        text_lower,
    )
    if next_match:
        day_name = next_match.group(1)
        if day_name in day_map:
            target_weekday = day_map[day_name]
            current_weekday = now.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
            else:
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            return target_date.strftime("%d/%m/%Y")

    if re.search(r"\btomorrow\b", text_lower) or re.search(r"\bmorgen\b", text_lower):
        target_date = now + timedelta(days=1)
        return target_date.strftime("%d/%m/%Y")

    if re.search(r"\btoday\b", text_lower) or re.search(r"\bvandaag\b", text_lower):
        return now.strftime("%d/%m/%Y")

    return None


def parse_days(days_line: Optional[str], dt: datetime) -> str:
    """Parse days line and return comma-separated string. Uses centralized parser."""
    if not days_line:
        return str(dt.weekday())

    days_list = parse_days_string(days_line)
    if days_list:
        return ",".join(sorted(set(days_list)))

    logger.debug(
        f"⚠️ Fallback triggered in parse_days — no valid days_line: '{days_line}' "
        f"→ weekday of dt: {dt.strftime('%A')} ({dt.weekday()})"
    )
    return str(dt.weekday())


def short_title_for_reminder_name(parsed: Dict, max_chars: int = 50) -> str:
    """
    Derive a short, clear title for the reminder name. When the embed title is long or
    duplicates the description (everything in one line), use the first line of the
    description or the first part of the title so the reminder name stays readable.
    Kept to ~50 chars so the sent reminder embed title stays concise.
    """
    title_val = (parsed.get("title") or "").strip() or "-"
    desc_val = (parsed.get("description") or "").strip() or ""

    def trim_at_word(text: str, limit: int) -> str:
        text = text.replace("\n", " ").replace("\r", " ")
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        part = text[: limit + 1].rsplit(" ", 1)
        result = part[0] if part[0] else text[:limit]
        return result[:limit]

    title_one_line = title_val.replace("\n", " ").strip()
    if len(title_one_line) <= max_chars and "\n" not in title_val:
        return trim_at_word(title_one_line, max_chars)

    if desc_val and desc_val != "-":
        first_line = desc_val.split("\n")[0].strip()
        first_line = " ".join(first_line.split())
        if first_line and len(first_line) <= max_chars:
            return first_line
        if first_line:
            return trim_at_word(first_line, max_chars)

    return trim_at_word(title_one_line, max_chars)


def format_message_paragraphs(text: str) -> str:
    """
    When the message is one long block (no or few newlines), add paragraph breaks
    after sentence endings so the reminder description is easier to read.
    Only applies when the text looks like a single block; preserves existing structure.
    """
    if not text or not text.strip():
        return text
    if text.count("\n") >= 2:
        return text
    formatted = re.sub(r"([a-z])\.\s+([A-Z])", r"\1.\n\n\2", text)
    formatted = re.sub(r"([a-z])\?\s+([A-Z])", r"\1?\n\n\2", formatted)
    formatted = re.sub(r"([a-z])\!\s+([A-Z])", r"\1!\n\n\2", formatted)
    formatted = re.sub(r"\s+\|\s+", "\n• ", formatted)
    return formatted.strip()
