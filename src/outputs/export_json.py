import json
import logging
from typing import Iterable
from ..parsers.review_extractor import ReviewRecord
from ..parsers.review_extractor import records_to_dicts

logger = logging.getLogger("amazon-reviews-scraper")

def export_json(records: Iterable[ReviewRecord], path: str) -> None:
    data = records_to_dicts(records)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Wrote JSON: %s", path)