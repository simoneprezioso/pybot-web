"""Optional DuckDuckGo search transport; no chatbot logic or model inference.

Importing this module uses only the standard library. The third-party client is
loaded only when a search is requested, so the ordinary bot works offline.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from html import unescape
from itertools import islice
import math
import re
import sys
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchResponse:
    results: Tuple[SearchResult, ...] = ()
    error: Optional[str] = None


def _load_ddgs():
    from ddgs import DDGS
    return DDGS


def _clean(value, limit):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", value,
                   flags=re.IGNORECASE | re.DOTALL)
    value = unescape(re.sub(r"<[^>]*>", " ", value))
    value = "".join(char if char.isprintable() else " " for char in value)
    value = " ".join(value.split())
    if len(value) > limit:
        value = value[:limit - 3].rsplit(" ", 1)[0] + "..."
    return value


def _url(value):
    if not isinstance(value, str):
        return None
    value = unescape(value)
    if any(char.isspace() or not char.isprintable() for char in value):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme.lower() not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None):
            return None
        # Accessing port validates malformed/non-numeric ports as well.
        parts.port
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                           parts.path, parts.query, ""))
    except ValueError:
        return None


def search(query, *, max_results=3, timeout=5, timelimit=None):
    """Return bounded, cleaned titles, URLs and snippets, or a safe error.

    ``timeout`` is the ddgs HTTP-client timeout in seconds. ``timelimit`` is
    ddgs' optional freshness filter (d, w, m or y). Search results are unverified
    excerpts, not facts. The DuckDuckGo backend is selected explicitly because
    ddgs otherwise chooses among several search engines.
    """
    if not isinstance(query, str) or not query.strip():
        return SearchResponse(error="Please provide a search query.")
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 10:
        return SearchResponse(error="Search result count must be between 1 and 10.")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        return SearchResponse(error="Search timeout must be a positive number of seconds.")
    if timelimit not in (None, "d", "w", "m", "y"):
        return SearchResponse(error="Search time limit must be d, w, m or y.")
    if sys.version_info < (3, 10):
        return SearchResponse(error="Web search requires Python 3.10 or newer; offline replies still work.")
    try:
        client_class = _load_ddgs()
    except (ImportError, SyntaxError):
        return SearchResponse(error="Web search needs the optional ddgs package. Install it with pip install '.[web]'.")
    except Exception:
        return SearchResponse(error="Web search is unavailable. Offline replies still work.")

    try:
        rows = client_class(timeout=timeout).text(
            " ".join(query.split()), max_results=max_results,
            backend="duckduckgo", timelimit=timelimit)
        results, seen = [], set()
        # Be bounded even if a client version returns an unbounded iterator.
        for row in islice(rows or (), max_results * 5):
            if not isinstance(row, Mapping):
                continue
            url = _url(row.get("href"))
            title = _clean(row.get("title"), 160)
            if not url or not title or url in seen:
                continue
            results.append(SearchResult(title, url, _clean(row.get("body"), 360)))
            seen.add(url)
            if len(results) == max_results:
                break
        return SearchResponse(tuple(results))
    except Exception as error:
        # ddgs' own timeout exception does not inherit Python's TimeoutError.
        # Avoid importing optional exception types when the package is absent.
        if isinstance(error, TimeoutError) or type(error).__name__ == "TimeoutException":
            return SearchResponse(error="Web search timed out. Please try again later.")
        if type(error).__name__ == "DDGSException" and str(error).strip().lower() == "no results found.":
            return SearchResponse()
        # Do not expose provider exception text: it can contain proxy credentials
        # or other connection details, and rate limiting is also recoverable.
        return SearchResponse(error="Web search is unavailable. Check your connection or try again later.")
