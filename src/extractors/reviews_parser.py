import logging
import re
import time
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .utils_text import clean_text, parse_helpful_votes, parse_rating_score

logger = logging.getLogger(__name__)

class AmazonReviewsScraper:
    """
    High-level scraper that:
    1. Derives the reviews listing URL from a product URL.
    2. Paginates through review pages.
    3. Extracts structured review data.
    """

    BASE_DOMAIN = "https://www.amazon.com"

    def __init__(
        self,
        user_agent: str,
        timeout: int = 20,
        proxy: Optional[str] = None,
        retry_count: int = 3,
        sleep_between_requests: float = 1.0,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.timeout = timeout
        self.retry_count = retry_count
        self.sleep_between_requests = sleep_between_requests
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    # ----------------------- Public API -----------------------

    def scrape_product_reviews(self, product_url: str, max_reviews: int = 100) -> List[Dict]:
        asin = self._extract_asin(product_url)
        if not asin:
            raise ValueError(f"Could not determine ASIN from product URL: {product_url}")

        logger.info("Derived ASIN %s from URL %s", asin, product_url)

        collected: List[Dict] = []
        page = 1

        while len(collected) < max_reviews:
            page_url = self._build_review_page_url(asin, page)
            logger.debug("Fetching reviews page %s: %s", page, page_url)
            html = self._fetch_html_with_retries(page_url)
            if not html:
                logger.warning("Empty HTML returned for %s. Stopping pagination.", page_url)
                break

            soup = BeautifulSoup(html, "lxml")
            reviews = list(self._parse_reviews_from_soup(soup, asin=asin, start_position=len(collected) + 1))

            if not reviews:
                logger.info("No more reviews found at page %s.", page)
                break

            collected.extend(reviews)
            logger.info("Page %s yielded %d reviews (total so far: %d).", page, len(reviews), len(collected))

            if len(collected) >= max_reviews:
                break

            page += 1
            time.sleep(self.sleep_between_requests)

        return collected[:max_reviews]

    # ----------------------- URL & HTTP Helpers -----------------------

    def _build_review_page_url(self, asin: str, page: int) -> str:
        return f"{self.BASE_DOMAIN}/product-reviews/{asin}?pageNumber={page}&sortBy=recent"

    def _fetch_html_with_retries(self, url: str) -> Optional[str]:
        for attempt in range(1, self.retry_count + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, proxies=self.proxies)
                if response.status_code == 200:
                    return response.text
                logger.warning("Non-200 status (%s) for %s", response.status_code, url)
            except requests.RequestException as exc:
                logger.warning("Request error (attempt %d/%d) for %s: %s", attempt, self.retry_count, url, exc)
            time.sleep(self.sleep_between_requests * attempt)
        logger.error("Failed to fetch %s after %d attempts.", url, self.retry_count)
        return None

    def _extract_asin(self, url: str) -> Optional[str]:
        """
        Attempt to extract the ASIN from various common Amazon URL formats.
        """
        parsed = urlparse(url)
        path = parsed.path

        # /dp/ASIN/...
        m = re.search(r"/dp/([A-Z0-9]{10})", path)
        if m:
            return m.group(1)

        # /gp/product/ASIN/...
        m = re.search(r"/gp/product/([A-Z0-9]{10})", path)
        if m:
            return m.group(1)

        # /product-reviews/ASIN or query parameter ASIN=
        m = re.search(r"/product-reviews/([A-Z0-9]{10})", path)
        if m:
            return m.group(1)

        m = re.search(r"[?&]ASIN=([A-Z0-9]{10})", parsed.query)
        if m:
            return m.group(1)

        # Fallback: last path segment of length 10
        segments = [seg for seg in path.split("/") if seg]
        for seg in segments[::-1]:
            if len(seg) == 10 and seg.isalnum():
                return seg

        return None

    # ----------------------- Parsing Helpers -----------------------

    def _parse_reviews_from_soup(
        self,
        soup: BeautifulSoup,
        asin: str,
        start_position: int = 1,
    ) -> Iterable[Dict]:
        review_blocks = soup.select("div[data-hook='review']")
        position = start_position
        for block in review_blocks:
            try:
                review = self._parse_single_review(block, asin=asin, position=position)
                if review:
                    yield review
                    position += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Error parsing review block: %s", exc, exc_info=True)
                continue

    def _parse_single_review(self, block: Tag, asin: str, position: int) -> Optional[Dict]:
        rating_text = ""
        rating_tag = block.select_one("i[data-hook='review-star-rating'] span.a-icon-alt") or block.select_one(
            "span.a-icon-alt"
        )
        if rating_tag:
            rating_text = rating_tag.get_text(strip=True)

        rating_score = parse_rating_score(rating_text)

        title_tag = block.select_one("a[data-hook='review-title'] span")
        if not title_tag:
            title_tag = block.select_one("a[data-hook='review-title']")
        review_title = clean_text(title_tag.get_text(strip=True)) if title_tag else ""

        link_tag = block.select_one("a[data-hook='review-title']")
        review_url = urljoin(self.BASE_DOMAIN, link_tag["href"]) if link_tag and link_tag.has_attr("href") else ""

        reaction_tag = block.select_one("span[data-hook='helpful-vote-statement']")
        review_reaction = clean_text(reaction_tag.get_text(strip=True)) if reaction_tag else "0 people found this helpful"

        reviewed_in_tag = block.select_one("span[data-hook='review-date']")
        reviewed_in = clean_text(reviewed_in_tag.get_text(strip=True)) if reviewed_in_tag else ""

        body_tag = block.select_one("span[data-hook='review-body'] span") or block.select_one(
            "span[data-hook='review-body']"
        )
        review_description = clean_text(body_tag.get_text(" ", strip=True)) if body_tag else ""

        verified_tag = block.select_one("span[data-hook='avp-badge']")
        is_verified = bool(verified_tag and "Verified Purchase" in verified_tag.get_text())

        variant_tag = block.select_one("a[data-hook='format-strip']")
        variant = clean_text(variant_tag.get_text(" ", strip=True)) if variant_tag else ""

        image_tags = block.select("img[data-hook='review-image-tile']")
        review_images = []
        for img in image_tags:
            src = img.get("src") or img.get("data-src")
            if src:
                review_images.append(src)

        if not review_description and not rating_score:
            # Too empty, probably not a real review.
            return None

        review: Dict = {
            "productAsin": asin,
            "ratingScore": rating_score,
            "reviewTitle": review_title,
            "reviewUrl": review_url,
            "reviewReaction": review_reaction,
            "reviewedIn": reviewed_in,
            "reviewDescription": review_description,
            "isVerified": is_verified,
            "variant": variant,
            "reviewImages": review_images,
            "position": position,
            "helpfulVotes": parse_helpful_votes(review_reaction),
        }
        return review