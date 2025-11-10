import csv
import json
import logging
from typing import Any, Dict, Iterable, List

from .storage_manager import StorageManager

logger = logging.getLogger(__name__)

class ReviewExporter:
    """
    Responsible for exporting review datasets to disk in various formats.
    """

    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage

    def to_json(self, reviews: Iterable[Dict[str, Any]], path: str) -> None:
        data = list(reviews)
        logger.info("Writing %d records to JSON file: %s", len(data), path)
        with self.storage.open_for_write(path, binary=False) as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def to_csv(self, reviews: Iterable[Dict[str, Any]], path: str) -> None:
        data: List[Dict[str, Any]] = list(reviews)
        if not data:
            logger.warning("No data provided to CSV exporter; nothing will be written to %s.", path)
            return

        logger.info("Writing %d records to CSV file: %s", len(data), path)
        fieldnames = sorted(data[0].keys())
        with self.storage.open_for_write(path, binary=False, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)