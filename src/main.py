import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Local imports
from parsers.review_extractor import ReviewExtractor, ReviewRecord
from parsers.utils_domain import DomainConfig
from outputs.export_json import export_json
from outputs.export_csv import export_csv
from outputs.export_excel import export_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("amazon-reviews-scraper")

def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_outdir(outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Amazon Reviews Scraper - extracts product reviews by ASIN."
    )
    parser.add_argument(
        "--input",
        "-i",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "sample_input.json"),
        help="Path to input JSON containing ASINs, domainCode, and options.",
    )
    parser.add_argument(
        "--settings",
        "-s",
        default=os.path.join(os.path.dirname(__file__), "config", "settings.example.json"),
        help="Path to settings JSON with defaults (proxies, headers, etc.).",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        default="out",
        help="Directory to write exported files.",
    )
    parser.add_argument(
        "--format",
        "-f",
        default="json",
        choices=["json", "csv", "excel"],
        help="Export format.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Generate synthetic data instead of making network requests.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override max pages per ASIN (reviews pagination).",
    )
    parser.add_argument(
        "--sort",
        choices=["recent", "helpful"],
        default=None,
        help="Sort strategy for reviews (if supported).",
    )
    return parser.parse_args()

def merge_settings(settings: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(settings or {})
    for k, v in (overrides or {}).items():
        if v is not None:
            merged[k] = v
    return merged

def main() -> int:
    args = parse_args()
    ensure_outdir(args.outdir)

    try:
        settings = load_json_file(args.settings)
    except FileNotFoundError:
        logger.warning("Settings file not found, using defaults.")
        settings = {}

    try:
        input_cfg = load_json_file(args.input)
    except Exception as e:
        logger.error("Failed to read input file %s: %s", args.input, e)
        return 1

    # Top-level defaults
    defaults = settings.get("defaults", {})
    domain_map = settings.get("domains", {})

    # Resolve runtime flags into defaults
    if args.max_pages is not None:
        defaults["maxPages"] = args.max_pages
    if args.sort is not None:
        defaults["sortBy"] = args.sort
    if args.mock:
        defaults["mock"] = True

    # Input payload may include multiple jobs
    jobs: List[Dict[str, Any]] = input_cfg.get("jobs") or [input_cfg]

    # Build domain config
    domain_cfg = DomainConfig(domain_map=domain_map, default_code=defaults.get("domainCode", "com"))

    extractor = ReviewExtractor(
        domain_cfg=domain_cfg,
        timeout=settings.get("network", {}).get("timeoutSeconds", 20),
        max_retries=settings.get("network", {}).get("maxRetries", 3),
        proxy=settings.get("network", {}).get("proxy"),
        user_agent=settings.get("network", {}).get("userAgent"),
    )

    all_records: List[ReviewRecord] = []
    for job in jobs:
        # Merge defaults with job-level params
        job_params = merge_settings(defaults, job)

        asins = job_params.get("asins") or ([job_params["asin"]] if "asin" in job_params else [])
        if not asins:
            logger.warning("Skipping job with no ASINs: %s", job_params)
            continue

        domain_code = job_params.get("domainCode", domain_cfg.default_code)
        max_pages = int(job_params.get("maxPages", 2))
        sort_by = job_params.get("sortBy", "recent")
        filters = {
            "filterByStar": job_params.get("filterByStar"),
            "filterByKeyword": job_params.get("filterByKeyword"),
            "verifiedOnly": bool(job_params.get("verifiedOnly", False)),
            "withMediaOnly": bool(job_params.get("withMediaOnly", False)),
        }
        mock = bool(job_params.get("mock", False))

        logger.info(
            "Starting job | domain=%s | asins=%s | max_pages=%s | sort=%s | mock=%s",
            domain_code,
            ",".join(asins),
            max_pages,
            sort_by,
            mock,
        )

        for asin in asins:
            try:
                records = extractor.fetch_reviews(
                    asin=asin,
                    domain_code=domain_code,
                    max_pages=max_pages,
                    filters=filters,
                    sort_by=sort_by,
                    mock=mock,
                )
                all_records.extend(records)
                logger.info("Collected %d reviews for ASIN %s", len(records), asin)
            except Exception as e:
                logger.exception("Failed to collect reviews for %s: %s", asin, e)

    # Export
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base_name = f"amazon_reviews_{timestamp}"

    if args.format == "json":
        out_path = os.path.join(args.outdir, f"{base_name}.json")
        export_json(all_records, out_path)
    elif args.format == "csv":
        out_path = os.path.join(args.outdir, f"{base_name}.csv")
        export_csv(all_records, out_path)
    elif args.format == "excel":
        out_path = os.path.join(args.outdir, f"{base_name}.xlsx")
        export_excel(all_records, out_path)
    else:
        logger.error("Unknown export format: %s", args.format)
        return 2

    logger.info("Exported %d records to %s", len(all_records), out_path)
    print(out_path)
    return 0

if __name__ == "__main__":
    sys.exit(main())