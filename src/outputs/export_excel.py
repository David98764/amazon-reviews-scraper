import logging
from typing import Iterable

import pandas as pd

from ..parsers.review_extractor import ReviewRecord
from ..parsers.review_extractor import records_to_dicts

logger = logging.getLogger("amazon-reviews-scraper")

def export_excel(records: Iterable[ReviewRecord], path: str) -> None:
    rows = records_to_dicts(records)
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="reviews")
    logger.info("Wrote Excel: %s", path)