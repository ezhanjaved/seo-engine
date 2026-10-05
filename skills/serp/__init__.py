"""SERP skill: collects search-results and ranking-page evidence, performs no analysis."""

from .collector import (
    BrowserStartupError,
    SerpAcquisitionError,
    SerpBlockedError,
    SerpError,
    SerpParseError,
    collect,
)
from .extractor import extract_page

__all__ = [
    "BrowserStartupError",
    "SerpAcquisitionError",
    "SerpBlockedError",
    "SerpError",
    "SerpParseError",
    "collect",
    "extract_page",
]
