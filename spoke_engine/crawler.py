from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from spoke_engine.config import host_allowed, load_and_validate, load_json, save_json


RELEVANCE_RE = re.compile(
    r"(?i)\b(application|apply|applicant|deadline|close[sd]?|closing|open(?:s|ed)?|"
    r"award|fund(?:ing|s|ed)?|scholarship|education savings account|ESA|priority|renewal|"
    r"eligible|eligibility|school year|program year)\b"
)
DATE_RE = re.compile(
    r"(?i)\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b20\d{2}[–-]\d{2,4}\b"
)
AMOUNT_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")
STATUS_RE = re.compile(
    r"(?i)\b(?:applications? (?:are |is )?(?:now )?(?:open|closed)|"
    r"no longer accepting applications|application window|priority application period|"
    r"reached (?:our |the )?(?:statutory )?(?:cap|limit))\b"
)
SPACE_RE = re.compile(r"\s+")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def extract_page(html: str, url: str) -> tuple[str, list[str], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script, style, noscript, nav, footer, form, svg"):
        node.decompose()
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else url)
    container = soup.select_one("main, article, [role='main']") or soup.body or soup
    blocks: list[str] = []
    for node in container.select("h1, h2, h3, p, li, td"):
        text = clean_text(node.get_text(" ", strip=True))
        if 30 <= len(text) <= 1200 and text not in blocks:
            blocks.append(text)
    links = [normalize_url(urljoin(url, anchor["href"])) for anchor in soup.select("a[href]")]
    return title, blocks, links


def candidate_facts(program_id: str, source: dict, url: str, title: str, blocks: list[str]) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    for block in blocks:
        if not RELEVANCE_RE.search(block):
            continue
        dates = list(dict.fromkeys(match.group(0) for match in DATE_RE.finditer(block)))
        amounts = list(dict.fromkeys(match.group(0) for match in AMOUNT_RE.finditer(block)))
        status = bool(STATUS_RE.search(block))
        if not dates and not amounts and not status:
            continue
        excerpt = block[:320].rstrip()
        normalized = excerpt.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        candidate_id = hashlib.sha256(
            f"{program_id}\n{url}\n{normalized}".encode("utf-8")
        ).hexdigest()[:16]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "program_id": program_id,
                "source_url": url,
                "source_title": title,
                "authority": source["authority"],
                "excerpt": excerpt,
                "dates_found": dates,
                "amounts_found": amounts,
                "status_language_found": status,
                "review_status": "needs_review",
            }
        )
    return candidates[:30]


class OfficialSourceCrawler:
    def __init__(self, root: str | Path, *, delay: float = 2.0, timeout: int = 30):
        self.root = Path(root)
        self.delay = max(0.5, delay)
        self.timeout = timeout
        contact = os.getenv("CRAWLER_CONTACT", "").strip()
        self.user_agent = os.getenv("CRAWLER_USER_AGENT", "").strip()
        if not self.user_agent:
            suffix = f"; mailto:{contact}" if contact else "; set CRAWLER_CONTACT"
            self.user_agent = f"TutoringProgramFactsBot/1.0 ({suffix})"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}
        self.cache_path = self.root / ".cache" / "http_metadata.json"
        self.snapshot_path = self.root / "data" / "crawl_snapshot.json"
        self.cache = load_json(self.cache_path) if self.cache_path.exists() else {}
        self.previous_snapshot = load_json(self.snapshot_path) if self.snapshot_path.exists() else {"pages": {}}
        self.pages: dict[str, dict] = {}
        self.errors: list[dict] = []

    def _wait(self, host: str) -> None:
        remaining = self.delay - (time.monotonic() - self._last_request.get(host, 0.0))
        if remaining > 0:
            time.sleep(remaining)
        self._last_request[host] = time.monotonic()

    def _robots_parser(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = f"{origin}/robots.txt"
        try:
            self._wait(parts.hostname or parts.netloc)
            response = self.session.get(robots_url, timeout=self.timeout)
            parser = RobotFileParser()
            parser.set_url(robots_url)
            if response.status_code == 404:
                parser.parse([])
            elif response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                self._robots[origin] = None
                return None
            self._robots[origin] = parser
            return parser
        except requests.RequestException:
            self._robots[origin] = None
            return None

    def _allowed_by_robots(self, url: str) -> bool:
        parser = self._robots_parser(url)
        return parser is not None and parser.can_fetch(self.user_agent, url)

    def _fetch(self, program_id: str, source: dict, url: str) -> dict | None:
        url = normalize_url(url)
        if not host_allowed(url, source["allowed_domains"]):
            self.errors.append({"program_id": program_id, "url": url, "error": "host_not_allowed"})
            return None
        if not self._allowed_by_robots(url):
            self.errors.append({"program_id": program_id, "url": url, "error": "robots_denied_or_unavailable"})
            return None

        cached = self.cache.get(url, {})
        headers: dict[str, str] = {}
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
        try:
            host = urlsplit(url).hostname or ""
            self._wait(host)
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 304:
                previous = self.previous_snapshot.get("pages", {}).get(url)
                if previous:
                    return previous
                response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                raise ValueError("source did not return HTML")
            title, blocks, links = extract_page(response.text, url)
            facts = candidate_facts(program_id, source, url, title, blocks)
            self.cache[url] = {
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "checked_at": utc_now(),
            }
            return {
                "program_id": program_id,
                "source_url": url,
                "source_title": title,
                "authority": source["authority"],
                "fetched_at": utc_now(),
                "content_hash": hashlib.sha256(response.content).hexdigest(),
                "candidates": facts,
                "links": links,
            }
        except (requests.RequestException, ValueError) as exc:
            self.errors.append({"program_id": program_id, "url": url, "error": str(exc)})
            return None

    def crawl(self, programs: dict[str, dict]) -> dict:
        for program_id, program in programs.items():
            for source in program.get("sources", []):
                queue = deque([(normalize_url(source["url"]), 0)])
                seen: set[str] = set()
                max_pages = max(1, min(int(source.get("max_pages", 1)), 10))
                while queue and len(seen) < max_pages:
                    url, depth = queue.popleft()
                    if url in seen:
                        continue
                    seen.add(url)
                    page = self._fetch(program_id, source, url)
                    if not page:
                        continue
                    self.pages[url] = page
                    if depth >= int(source.get("max_depth", 0)):
                        continue
                    patterns = source.get("follow_patterns", [])
                    for link in page.get("links", []):
                        if (
                            link not in seen
                            and host_allowed(link, source["allowed_domains"])
                            and any(re.search(pattern, link) for pattern in patterns)
                        ):
                            queue.append((link, depth + 1))

        candidates = [
            candidate
            for page in self.pages.values()
            for candidate in page.get("candidates", [])
        ]
        output = {
            "generated_at": utc_now(),
            "review_required": True,
            "candidates": sorted(candidates, key=lambda row: (row["program_id"], row["source_url"], row["candidate_id"])),
            "errors": self.errors,
        }
        snapshot = {"generated_at": utc_now(), "pages": self.pages}
        save_json(self.cache_path, self.cache)
        save_json(self.snapshot_path, snapshot)
        save_json(self.root / "data" / "candidates.json", output)
        self._write_report(output)
        return output

    def _write_report(self, output: dict) -> None:
        old_ids = {
            item["candidate_id"]
            for page in self.previous_snapshot.get("pages", {}).values()
            for item in page.get("candidates", [])
        }
        new_ids = {item["candidate_id"] for item in output["candidates"]}
        added = new_ids - old_ids
        removed = old_ids - new_ids
        lines = [
            "# Weekly source change report",
            "",
            f"Generated: {output['generated_at']}",
            "",
            f"- Candidate facts found: {len(new_ids)}",
            f"- New or changed candidates: {len(added)}",
            f"- Candidates no longer observed: {len(removed)}",
            f"- Fetch errors: {len(output['errors'])}",
            "",
            "No candidate is published until a person verifies it against the linked source and adds it to `data/approved_facts.json`.",
            "",
            "## New or changed candidates",
            "",
        ]
        by_id = {item["candidate_id"]: item for item in output["candidates"]}
        for candidate_id in sorted(added):
            item = by_id[candidate_id]
            lines.extend(
                [
                    f"### {item['program_id']} — `{candidate_id}`",
                    "",
                    f"Source: {item['source_url']}",
                    "",
                    f"> {item['excerpt']}",
                    "",
                ]
            )
        if output["errors"]:
            lines.extend(["## Fetch errors", ""])
            for error in output["errors"]:
                lines.append(f"- `{error['program_id']}` {error['url']}: {error['error']}")
        report = self.root / "reports" / "change_report.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_crawl(root: str | Path, *, strict: bool = False, delay: float = 2.0) -> dict:
    _, programs = load_and_validate(root)
    crawler = OfficialSourceCrawler(root, delay=delay)
    result = crawler.crawl(programs)
    if strict and result["errors"]:
        raise RuntimeError(f"{len(result['errors'])} official-source fetches failed; see reports/change_report.md")
    return result

