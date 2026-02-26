"""
Input sanitization utilities for Discord bot security.

Prevents markdown injection, mention spam, prompt injection attacks,
and embed exploits by sanitizing user input before it reaches
embeds, LLM prompts, logs, or other sensitive contexts.
"""

import re
from typing import Optional


def escape_markdown(text: str) -> str:
    """
    Escapes Discord markdown characters to prevent injection.
    
    Escapes: *, _, ~, `, |, >, [, ]
    
    Args:
        text: Input text that may contain markdown
        
    Returns:
        Text with markdown characters escaped
    """
    if not text:
        return ""
    
    # Escape Discord markdown characters
    # Order matters: escape backticks first to avoid double-escaping
    text = text.replace("\\", "\\\\")  # Escape backslashes first
    text = text.replace("`", "\\`")    # Code blocks
    text = text.replace("*", "\\*")    # Bold/italic
    text = text.replace("_", "\\_")    # Underline/italic
    text = text.replace("~", "\\~")   # Strikethrough
    text = text.replace("|", "\\|")    # Spoiler
    text = text.replace(">", "\\>")    # Quote
    text = text.replace("[", "\\[")    # Links
    text = text.replace("]", "\\]")    # Links
    
    return text


def strip_mentions(text: str) -> str:
    """
    Removes Discord mentions to prevent mention spam.
    
    Removes: user mentions (<@123456>), role mentions (<@&123456>),
    channel mentions (<#123456>), @everyone, @here
    
    Args:
        text: Input text that may contain mentions
        
    Returns:
        Text with all mentions removed
    """
    if not text:
        return ""
    
    # Remove user mentions: <@123456> or <@!123456>
    text = re.sub(r"<@!?\d+>", "", text)
    
    # Remove role mentions: <@&123456>
    text = re.sub(r"<@&\d+>", "", text)
    
    # Remove channel mentions: <#123456>
    text = re.sub(r"<#\d+>", "", text)
    
    # Remove @everyone and @here (case insensitive)
    text = re.sub(r"@everyone", "", text, flags=re.IGNORECASE)
    text = re.sub(r"@here", "", text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


def url_filter(text: str, allow_http: bool = False) -> str:
    """
    Filters or sanitizes URLs in text.
    
    Args:
        text: Input text that may contain URLs
        allow_http: If True, allows http/https URLs. If False, removes all URLs.
        
    Returns:
        Text with URLs filtered according to allow_http setting
    """
    if not text:
        return ""
    
    if allow_http:
        # Only remove non-http/https URLs (javascript:, data:, vbscript:, etc.)
        # Use explicit protocol removal to avoid variable-width lookbehind (unsupported in Python re)
        dangerous_protocols = (
            r"javascript:[^\s]*",
            r"data:[^\s]*",
            r"vbscript:[^\s]*",
            r"file:[^\s]*",
        )
        for pattern in dangerous_protocols:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    else:
        # Remove all URLs
        # Match http://, https://, and protocol-relative URLs
        text = re.sub(r"https?://[^\s]+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"//[^\s]+", "", text)
        # Also match URLs without protocol (www.example.com)
        text = re.sub(r"\bwww\.[^\s]+", "", text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


def safe_embed_text(text: str, max_length: int = 4096) -> str:
    """
    Sanitizes text for use in Discord embed titles, descriptions, or fields.

    Combines url_filter, strip_mentions, and escape_markdown, then truncates to max_length.

    Args:
        text: Input text to sanitize
        max_length: Maximum length (Discord embed limit is 4096 for description)

    Returns:
        Safe text ready for embed use
    """
    if not text:
        return ""

    # Remove URLs, strip mentions, then escape markdown
    text = url_filter(text, allow_http=False)
    text = strip_mentions(text)
    text = escape_markdown(text)
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."
    
    return text


def safe_prompt(user_input: str, context: Optional[str] = None) -> str:
    """
    Sanitizes user input for LLM prompts to prevent prompt injection attacks.
    
    Detects and neutralizes common jailbreak patterns:
    - "ignore previous", "forget instructions"
    - "act as", "you are now"
    - "system:", "new instructions"
    - "override", "pretend"
    
    Args:
        user_input: Raw user input that may contain injection attempts
        context: Optional context string to prepend to the sanitized input
        
    Returns:
        Sanitized prompt-safe string
    """
    if not user_input:
        return context or ""
    
    # Convert to lowercase for pattern matching
    lower_input = user_input.lower()
    
    # Jailbreak patterns to detect and neutralize
    jailbreak_patterns = [
        r"ignore\s+(previous|all|the)\s+(instructions?|prompt|system)",
        r"forget\s+(all\s+)?(previous|the)\s+(instructions?|prompt|system)",
        r"disregard\s+(previous|all|the)\s+(instructions?|prompt|system)",
        r"act\s+as\s+(if\s+)?(you\s+are\s+)?",
        r"you\s+are\s+now\s+",
        r"system\s*:\s*",
        r"new\s+instructions?\s*:",
        r"override\s+(previous|the)\s+",
        r"pretend\s+(you\s+are\s+)?(that\s+you\s+are\s+)?",
        r"you\s+are\s+dan\s*\(.*?\)",
        r"ignore\s+the\s+system\s+prompt",
        r"bypass\s+(previous|the)\s+",
        r"disregard\s+the\s+above",
    ]
    
    # Check for jailbreak attempts
    is_jailbreak = False
    for pattern in jailbreak_patterns:
        if re.search(pattern, lower_input, re.IGNORECASE):
            is_jailbreak = True
            break
    
    # If jailbreak detected, neutralize it
    if is_jailbreak:
        # Remove the jailbreak pattern and sanitize
        for pattern in jailbreak_patterns:
            user_input = re.sub(pattern, "", user_input, flags=re.IGNORECASE)
        # Add warning marker
        user_input = f"[User input sanitized] {user_input.strip()}"
    
    # Escape dangerous characters that could break prompt structure
    # Remove or escape control characters
    user_input = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", user_input)
    
    # Escape newlines that could break prompt structure (replace with space)
    user_input = user_input.replace("\n", " ").replace("\r", " ")
    
    # Clean up extra whitespace
    user_input = re.sub(r"\s+", " ", user_input).strip()
    
    # Combine with context if provided
    if context:
        return f"{context} {user_input}"
    
    return user_input


def safe_log_message(text: str, max_length: int = 200) -> str:
    """
    Sanitizes text for logging to prevent log injection and spam.
    
    Escapes newlines and control characters, truncates to max_length.
    
    Args:
        text: Input text to sanitize for logging
        max_length: Maximum length (default 200 to prevent log spam)
        
    Returns:
        Safe text ready for logging
    """
    if not text:
        return ""
    
    # Convert to string if not already
    text = str(text)
    
    # Remove control characters (except newlines initially)
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    
    # Replace newlines and carriage returns with spaces
    text = text.replace("\n", " ").replace("\r", " ")
    
    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."
    
    return text
