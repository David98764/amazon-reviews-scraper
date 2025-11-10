import csv
import logging
from typing import Iterable

from ..parsers.review_extractor import ReviewRecord
from ..parsers.review_extractor import records_to_dicts

logger = logging.getLogger("amazon-reviews-scraper")

def export_csv(records: Iterable[ReviewRecord], path: str) -> None:
    rows = records_to_dicts(records)
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        logger.info("No records; wrote empty CSV: %s", path)
        return

    # Use union of all keys for robustness
    fieldnames = set()
    for r in rows:
        fieldnames.update(r.keys())
    field_list = sorted(fieldnames)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=field_list)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    logger.info("Wrote CSV: %s", path)