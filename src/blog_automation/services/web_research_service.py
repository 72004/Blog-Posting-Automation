from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebResearchService:
    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results

    def search(self, query: str) -> list[SearchResult]:
        return []

    def fetch_article_text(self, url: str) -> str:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = [paragraph.get_text(" ", strip=True) for paragraph in soup.find_all("p")]
        return "\n".join(paragraphs)

    def summarize_results(self, results: list[SearchResult]) -> dict[str, Any]:
        return {
            "results": [result.__dict__ for result in results],
            "insights": [],
            "faqs": [],
            "statistics": [],
        }