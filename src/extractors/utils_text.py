import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_HELPFUL_RE = re.compile(r"(\d+)\s+people? found this helpful", re.IGNORECASE)
_RATING_RE = re.compile(r"([0-5](?:\.\d)?)\s+out of\s+5", re.IGNORECASE)

def clean_text(text: str) -> str:
    """
    Normalize whitespace and strip stray characters from a string.
    """
    if text is None:
        return ""
    cleaned = " ".join(text.split())
    return cleaned.strip()

def parse_helpful_votes(text: str) -> int:
    """
    Parse the number of helpful votes from a text like:
    "21 people found this helpful" or "One person found this helpful".
    """
    if not text:
        return 0

    match = _HELPFUL_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            logger.debug("Failed to parse helpful votes from %s", text)

    text_lower = text.lower()
    if "one person found this helpful" in text_lower:
        return 1

    return 0

def parse_rating_score(text: str) -> Optional[float]:
    """
    Parse rating from text like "4.0 out of 5 stars".
    Returns None if parsing fails.
    """
    if not text:
        return None
    match = _RATING_RE.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            logger.debug("Failed to parse rating score from %s", text)
    return None