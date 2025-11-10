import json
import logging
import random
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from .utils_domain import DomainConfig

logger = logging.getLogger("amazon-reviews-scraper")

@dataclass
class ReviewRecord:
    statusCode: int
    statusMessage: str
    asin: str
    productTitle: Optional[str]
    currentPage: int
    sortStrategy: str
    countReviews: int
    domainCode: str
    filters: Dict[str, Any]
    countRatings: Optional[int]
    productRating: Optional[str]
    reviewSummary: Optional[Dict[str, Any]]
    reviewId: Optional[str]
    text: Optional[str]
    date: Optional[str]
    rating: Optional[str]
    title: Optional[str]
    userName: Optional[str]
    numberOfHelpful: Optional[int]
    variationId: Optional[str]
    imageUrlList: Optional[List[str]]
    videoUrlList: Optional[List[str]]
    variationList: Optional[List[str]]
    verified: Optional[bool]
    vine: Optional[bool]

class ReviewExtractor:
    def __init__(
        self,
        domain_cfg: DomainConfig,
        timeout: int = 20,
        max_retries: int = 3,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self.domain_cfg = domain_cfg
        self.timeout = timeout
        self.max_retries = max_retries
        self.proxy = proxy
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    # -------------------- Public API --------------------

    def fetch_reviews(
        self,
        asin: str,
        domain_code: str,
        max_pages: int = 2,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "recent",
        mock: bool = False,
    ) -> List[ReviewRecord]:
        """Fetch reviews across pages. In mock mode, returns synthetic data."""
        filters = filters or {}
        if mock:
            return self._generate_mock(asin, domain_code, max_pages, filters, sort_by)

        records: List[ReviewRecord] = []
        product_info = None
        summary_info = None

        for page in range(1, max_pages + 1):
            url = self._build_reviews_url(asin, domain_code, page, sort_by, filters)
            logger.debug("Fetching page %s: %s", page, url)
            html = self._http_get(url)
            if not html:
                logger.warning("Empty HTML for %s page %d", asin, page)
                break

            soup = BeautifulSoup(html, "html.parser")

            # Extract product meta (once)
            if product_info is None:
                product_info = self._parse_product_info(soup)
            if summary_info is None:
                summary_info = self._parse_summary_info(soup)

            page_reviews = list(self._parse_reviews_from_soup(soup))
            logger.debug("Parsed %d reviews on page %d", len(page_reviews), page)

            for r in page_reviews:
                record = ReviewRecord(
                    statusCode=200,
                    statusMessage="FOUND",
                    asin=asin,
                    productTitle=product_info.get("title") if product_info else None,
                    currentPage=page,
                    sortStrategy=sort_by,
                    countReviews=len(page_reviews),
                    domainCode=domain_code,
                    filters=filters,
                    countRatings=summary_info.get("countRatings") if summary_info else None,
                    productRating=summary_info.get("productRating") if summary_info else None,
                    reviewSummary=summary_info.get("summary") if summary_info else None,
                    reviewId=r.get("id"),
                    text=r.get("text"),
                    date=r.get("date"),
                    rating=r.get("rating"),
                    title=r.get("title"),
                    userName=r.get("user"),
                    numberOfHelpful=r.get("helpful"),
                    variationId=r.get("variationId"),
                    imageUrlList=r.get("images"),
                    videoUrlList=r.get("videos"),
                    variationList=r.get("variations"),
                    verified=r.get("verified"),
                    vine=r.get("vine"),
                )
                records.append(record)

            # Be a good citizen
            time.sleep(random.uniform(0.8, 1.8))

        return records

    # -------------------- Networking --------------------

    def _http_get(self, url: str) -> Optional[str]:
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        headers = {"User-Agent": self.user_agent, "Accept-Language": "en-US,en;q=0.9"}
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(url, timeout=self.timeout, headers=headers, proxies=proxies)
                if resp.status_code == 200:
                    return resp.text
                logger.warning("HTTP %s for %s (attempt %d)", resp.status_code, url, attempt)
            except Exception as e:
                last_exc = e
                logger.warning("Request error (attempt %d): %s", attempt, e)
            time.sleep(0.5 * attempt)
        if last_exc:
            logger.error("Failed to GET %s after %d attempts: %s", url, self.max_retries, last_exc)
        return None

    # -------------------- Parsers --------------------

    def _build_reviews_url(
        self,
        asin: str,
        domain_code: str,
        page: int,
        sort_by: str,
        filters: Dict[str, Any],
    ) -> str:
        domain = self.domain_cfg.get_domain(domain_code)
        base = f"https://www.amazon.{domain}/product-reviews/{asin}"
        params = {
            "pageNumber": page,
            "sortBy": "recent" if sort_by == "recent" else "helpful",
        }
        if filters.get("filterByStar"):
            params["filterByStar"] = filters["filterByStar"]
        if filters.get("filterByKeyword"):
            params["filterByKeyword"] = filters["filterByKeyword"]
        if filters.get("verifiedOnly"):
            params["reviewerType"] = "avp_only_reviews"
        q = urlencode(params)
        return f"{base}/ref=cm_cr_arp_d_paging_btm_next_{page}?{q}"

    def _parse_product_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        # Title from header
        title = None
        h1 = soup.select_one("#cm_cr-product_info .product-title, #cm_cr-product_info h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            # Try from breadcrumbs / link
            link = soup.select_one("#cm_cr-product_info a[data-hook='product-link']")
            if link:
                title = link.get_text(strip=True)

        return {"title": title}

    def _parse_summary_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        product_rating = None
        count_ratings = None
        summary = {}

        avg = soup.select_one("span[data-hook='rating-out-of-text']")
        if avg:
            product_rating = avg.get_text(strip=True)

        cnt = soup.select_one("div[data-hook='total-review-count'] span")
        if cnt:
            try:
                count_ratings = int(re.sub(r"[^\d]", "", cnt.get_text()))
            except Exception:
                count_ratings = None

        # Distribution bars
        for star in ["five", "four", "three", "two", "one"]:
            el = soup.select_one(f"table#histogramTable tr.{star}-star .a-text-right")
            if el:
                m = re.search(r"(\d+)%", el.get_text())
                if m:
                    summary[f"{star}Star"] = {"percentage": int(m.group(1))}

        return {"productRating": product_rating, "countRatings": count_ratings, "summary": summary or None}

    def _parse_reviews_from_soup(self, soup: BeautifulSoup) -> Iterable[Dict[str, Any]]:
        for rev in soup.select("div[data-hook='review']"):
            rid = rev.get("id")
            title_el = rev.select_one("a[data-hook='review-title'] span")
            title = title_el.get_text(strip=True) if title_el else None

            rating_el = rev.select_one("i[data-hook='review-star-rating'] span, i[data-hook='cmps-review-star-rating'] span")
            rating = rating_el.get_text(strip=True) if rating_el else None

            user_el = rev.select_one("span.a-profile-name")
            user = user_el.get_text(strip=True) if user_el else None

            date_el = rev.select_one("span[data-hook='review-date']")
            date_txt = date_el.get_text(strip=True) if date_el else None

            text_el = rev.select_one("span[data-hook='review-body'] span")
            text = text_el.get_text(" ", strip=True) if text_el else None

            helpful_el = rev.select_one("span[data-hook='helpful-vote-statement']")
            helpful = None
            if helpful_el:
                m = re.search(r"(\d+)", helpful_el.get_text())
                helpful = int(m.group(1)) if m else 0

            verified = bool(rev.select_one("span[data-hook='avp-badge']"))
            vine = bool(rev.select_one("span[data-hook='vine-review-badge']"))

            images = [img.get("src") for img in rev.select("img.review-image-tile") if img.get("src")]
            videos = []
            for v in rev.select("div[data-hook='video-cmp'] video source"):
                if v.get("src"):
                    videos.append(v.get("src"))

            variations = []
            var_el = rev.select_one("a[data-hook='format-strip']")
            if var_el:
                variations.append(var_el.get_text(" ", strip=True))

            # Some pages include variationId in data; here we leave None
            yield {
                "id": rid,
                "title": title,
                "rating": rating,
                "user": user,
                "date": date_txt,
                "text": text,
                "helpful": helpful,
                "verified": verified,
                "vine": vine,
                "images": images or None,
                "videos": videos or None,
                "variations": variations or None,
                "variationId": None,
            }

    # -------------------- Mock Data --------------------

    def _generate_mock(
        self,
        asin: str,
        domain_code: str,
        max_pages: int,
        filters: Dict[str, Any],
        sort_by: str,
    ) -> List[ReviewRecord]:
        random.seed(hash((asin, domain_code)) & 0xFFFFFFFF)
        total = random.randint(5, 15) * max_pages
        product_title = f"Mock Product for {asin}"
        product_rating = f"{round(random.uniform(3.8, 4.9), 1)} out of 5"
        summary = {
            "fiveStar": {"percentage": random.randint(50, 90)},
            "fourStar": {"percentage": random.randint(5, 30)},
            "threeStar": {"percentage": random.randint(1, 15)},
            "twoStar": {"percentage": random.randint(0, 5)},
            "oneStar": {"percentage": random.randint(0, 5)},
        }
        records: List[ReviewRecord] = []
        for page in range(1, max_pages + 1):
            page_size = random.randint(5, 12)
            for i in range(page_size):
                rid = f"R{random.randint(10**12, 10**13-1)}"
                stars = random.choice([5, 4, 3, 2, 1])
                rec = ReviewRecord(
                    statusCode=200,
                    statusMessage="FOUND",
                    asin=asin,
                    productTitle=product_title,
                    currentPage=page,
                    sortStrategy=sort_by,
                    countReviews=page_size,
                    domainCode=domain_code,
                    filters=filters,
                    countRatings=total,
                    productRating=product_rating,
                    reviewSummary=summary,
                    reviewId=rid,
                    text=f"This is a mock review text {rid} for ASIN {asin}. Works well.",
                    date=datetime.utcnow().strftime("Reviewed on %d %B %Y"),
                    rating=f"{stars}.0 out of 5 stars",
                    title=f"Great product ({stars}★)",
                    userName=random.choice(["Alex", "Jordan", "Taylor", "Sam", "Casey", "Riley"]),
                    numberOfHelpful=random.randint(0, 25),
                    variationId=asin,
                    imageUrlList=None,
                    videoUrlList=None,
                    variationList=[random.choice(["Color: Black", "Size: Large", "Style: Single"])],
                    verified=random.choice([True, False, True]),
                    vine=False,
                )
                records.append(rec)
        return records

def records_to_dicts(records: Iterable[ReviewRecord]) -> List[Dict[str, Any]]:
    return [asdict(r) for r in records]