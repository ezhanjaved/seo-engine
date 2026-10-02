"""Google Search Console skill: retrieves performance data, performs no analysis."""

from .client import query_search_analytics, resolve_property

__all__ = ["query_search_analytics", "resolve_property"]
