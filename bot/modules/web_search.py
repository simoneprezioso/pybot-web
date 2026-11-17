"""Opt-in public web lookups, proposed through the normal module interface.

Only this module's respond hook performs I/O. Arbiter declarations are pure routing
checks: the arbiter may ask them more than once. Priority stays below safety (9000).
Search snippets are excerpts, never treated as independently verified facts.
"""
import copy
import importlib.util
import os
import random
import re
import sys
from functools import lru_cache

from .. import search as web
from ..knowledge.maths import solve
from ..memory.topics import in_a_safety_thread

PRIORITY = 8000

_EXPLICIT = re.compile(
    r"^(?:(?:please|can you|could you|would you)\s+)*"
    r"(?:search(?:\s+(?:the\s+)?(?:web|internet|online|duckduckgo))?(?:\s+for)?|"
    r"look\s+up|find\s+(?:online|on\s+(?:the\s+)?(?:web|internet)))\s+(.+)$", re.I)
_QUESTION = re.compile(
    r"^(?:who|what|when|where|how|which|is|are|has|have|did|does|do|will|"
    r"show|tell|give|any)\b", re.I)
_FRESH = re.compile(
    r"\b(?:current|currently|latest|recent|recently|today|tonight|now|"
    r"this\s+(?:week|month|year)|up[- ]to[- ]date|breaking|live)\b", re.I)
_PERSONAL = re.compile(r"\b(?:my|our|your|i|we)\b|\b(?:you (?:said|told)|did you tell)\b", re.I)
_ROLE = re.compile(
    r"\b(?:ceo|chief executive(?: officer)?|president|prime minister|"
    r"chancellor|governor|mayor|chairperson|chairman)\b", re.I)
_ROLE_ASK = re.compile(r"^(?:who(?:\s+is|'s)|what(?:\s+is|'s)|which)\b", re.I)
_ROLE_DUTIES = re.compile(r"\b(?:responsible|responsibilities|duties|role|job|salary|meaning|definition)\b", re.I)
_HISTORICAL = re.compile(
    r"\b(?:was|were|former|previous|first|history|historical|born|died)\b|"
    r"\b(?:in|during|before|after)\s+\d{4}\b", re.I)
_NEWS = re.compile(r"\b(?:news|headlines)\b", re.I)
_NEWS_DEFINITION = re.compile(
    r"\b(?:article|journalism|journalist|reporter|definition|mean|means|write|writing|affect|affects)\b", re.I)
_WEATHER = re.compile(r"\b(?:weather|forecast|temperature)\b", re.I)
_MARKET = re.compile(
    r"\b(?:stock|shares|bitcoin|ethereum|crypto(?:currency)?|exchange rate|"
    r"usd|eur|gbp)\b", re.I)
_PRICE = re.compile(r"\b(?:price|worth|cost|value|rate|trading|how much)\b", re.I)
_CHANGING = re.compile(
    r"\b(?:version|release|released|update|score|scores|results|standings|"
    r"election|elections|polls|population|inflation|unemployment|events)\b", re.I)
_DEFINITION = re.compile(
    r"^(?:(?:what(?:'s| is| are)|define|explain)\s+(?:a|an)\b|"
    r"(?:what(?:'s| is| are)|define|explain)\s+(?:the\s+)?"
    r"(?:ceo|chief executive officer|president|news|weather|temperature|"
    r"forecast|stock price|exchange rate|inflation|population)[?.!]*$)", re.I)
_EVENT_ASK = re.compile(
    r"^what(?:'s|s| is| has)?\s+(?:going on|happening|happened|new)\b", re.I)
_PERSON_ASK = re.compile(
    r"^who(?:\s+is|'s|s)\s+([a-z][a-z'.-]*(?:\s+[a-z][a-z'.-]*){1,3})[?!.]*$", re.I)
_NAME_STOP = frozenset((
    "a an the at in on of for to by with responsible best good bad who what where "
    "my our your his her their this that me you us them mother father brother sister "
    "friend neighbour neighbor boss colleague partner husband wife".split()))
_CAPABILITY = re.compile(
    r"(?:(?:can|could|do|will) you (?:"
    r"(?:web|internet) search|search(?: (?:the )?(?:web|internet|online|duckduckgo))?|"
    r"browse(?: (?:the )?(?:web|internet))?|access (?:the )?(?:web|internet)|"
    r"have (?:internet|web)(?: access)?)|"
    r"is (?:web|internet) search (?:enabled|disabled|on|off))", re.I)


def enabled():
    """Installing the dependency alone never enables network access."""
    return os.environ.get("PYBOT_WEB_SEARCH", "").strip().lower() in ("1", "true", "yes", "on")


def _package_available():
    try:
        return importlib.util.find_spec("ddgs") is not None
    except (ImportError, ValueError):
        return False


def status_message():
    """Describe configuration without importing ddgs or making a request."""
    if not enabled():
        return "Web search is off. Start with --web-search to enable it."
    if sys.version_info < (3, 10):
        return "Web search requires Python 3.10 or newer. Local replies are available."
    if not _package_available():
        return ('Web search is enabled, but ddgs is not installed. '
                'Install it with python -m pip install ".[web]".')
    return 'Web search is enabled (DuckDuckGo). Ask "search the web for ...".'


def _capability_question(text):
    if not isinstance(text, str):
        return False
    clean = " ".join(text.lower().split()).rstrip(" ?!.")
    return _CAPABILITY.fullmatch(clean) is not None


@lru_cache(maxsize=128)
def _known_locally(clean):
    from ..knowledge.lookup import find
    return find({"clean": clean.lower()}) is not None


def _person_lookup(asked, memory):
    person = _PERSON_ASK.fullmatch(asked)
    if not person:
        return False
    name = person.group(1).lower()
    if _NAME_STOP.intersection(name.split()) or _known_locally(asked):
        return False
    # Names introduced in conversation belong to memory, not a public lookup.
    for turn in (memory or {}).get("turns", ()):
        previous = turn.get("user", "").lower()
        if name in previous and not (_QUESTION.match(previous) or _EXPLICIT.match(previous)):
            return False
    return True


def query_for(text, memory=None):
    """Return a natural-language query only for a deliberately narrow rule match.

    Stable definitions, personal questions and ordinary conversation stay local.
    Unsupported shapes can be requested explicitly with 'search the web for'.
    The existing calculator also has date/conversion rules; keep those when they fit.
    """
    if not isinstance(text, str) or in_a_safety_thread(memory):
        return None
    clean = " ".join(text.replace("\u2019", "'").split()).strip()
    explicit = _EXPLICIT.match(clean)
    if explicit:
        return explicit.group(1).strip() or None
    if not clean or _PERSONAL.search(clean):
        return None
    # Strip conversational requests without treating a personal statement as a query.
    asked = re.sub(r"^(?:please\s+)?(?:can|could|would) you\s+(?:tell me\s+)?", "", clean, flags=re.I)
    asked = re.sub(r"^(?:please\s+)?(?:tell me|show me|give me)\s+", "", asked, flags=re.I)
    if _DEFINITION.search(asked):
        return None
    question = bool(_QUESTION.match(asked))
    fresh = bool(_FRESH.search(asked))
    brief = bool(len(asked.split()) <= 12 and not re.match(
        r"^(?:i|we|he|she|they|it)\b", asked, re.I) and not re.search(
        r"\b(?:is|are|was|were|seems?|looks?|feels?|makes?|made|has|have|had|"
        r"will|can|do|does|did)\b", asked, re.I))
    news = bool(_NEWS.search(asked) and not _NEWS_DEFINITION.search(asked))
    role = bool((_ROLE_ASK.match(asked) or (fresh and brief))
                and _ROLE.search(asked) and not _HISTORICAL.search(asked)
                and not _ROLE_DUTIES.search(asked))
    weather = bool(_WEATHER.search(asked) and (fresh or re.search(
        r"^(?:what(?:'s| is)\s+(?:the\s+)?(?:weather|forecast|temperature)\b.+|"
        r"(?:weather|forecast)\s+(?:in|for)\s+.+)$", asked, re.I))
        and not re.search(r"\b(?:mean|means|physics|affect|affects|work|works)\b|"
                          r"^(?:why|how does|how do)\b", asked, re.I))
    market = bool(_MARKET.search(asked) and _PRICE.search(asked) and not _HISTORICAL.search(asked))
    changing = bool(fresh and _CHANGING.search(asked) and not _HISTORICAL.search(asked))
    events = bool(fresh and _EVENT_ASK.match(asked))
    person = _person_lookup(asked, memory)
    # Short topic requests ("AI news today", "weather in Rome") need no question mark.
    if not (role or person or events or ((question or brief) and (news or weather or market or changing))):
        return None
    try:
        if solve(clean, {"clean": clean.lower()}, {}):
            return None
    except Exception:  # A missing local calculation must not break the search module.
        pass
    return clean


def _timelimit(query):
    if re.search(r"\b(?:today|tonight|breaking|past 24 hours)\b", query, re.I):
        return "d"
    if re.search(r"\b(?:this|past) week\b", query, re.I):
        return "w"
    if re.search(r"\b(?:this|past) month\b", query, re.I):
        return "m"
    return None


def _excerpt(text, limit):
    """Keep excerpts readable and bounded without inferring an answer from them."""
    text = " ".join("".join(char if char.isprintable() else " " for char in text).split())
    if len(text) <= limit:
        return text
    return text[:limit - 3].rsplit(" ", 1)[0] + "..."


def _safety_has_answer(text, memory):
    """Reuse existing emergency rules before I/O, preserving memory and wording.

    All responders run even when safety already proposed a reply. Asking its rules
    on an isolated copy avoids a network wait on that turn. Preserve random state
    because those rules choose reply wording, which we discard here.
    """
    from . import a_count_of_packets, safety

    state = random.getstate()
    try:
        return any(module.respond(text, copy.deepcopy(memory))
                   for module in (safety, a_count_of_packets))
    finally:
        random.setstate(state)


def respond(text, memory):
    if in_a_safety_thread(memory):
        return None
    if _capability_question(text):
        # Different capability questions must not be mistaken for a repeated
        # answer and replaced by an upstream "no internet" response.
        return 'About "%s": %s' % (_excerpt(text, 160), status_message())
    if not enabled():
        return None
    query = query_for(text, memory)
    if not query or _safety_has_answer(text, memory):
        return None
    response = web.search(query, max_results=3, timeout=5, timelimit=_timelimit(query))
    # Identify the query so the arbiter's repetition guards do not replace equal
    # search excerpts for different questions with an unrelated local answer.
    label = 'for "%s"' % _excerpt(query, 160)
    if response.error:
        return "Web search unavailable " + label + ": " + response.error + " I can't verify current information."
    if not response.results:
        return ("No useful search results found " + label + ". DuckDuckGo may have no matches "
                "or may be blocking automated requests. Try again later or use a more specific query.")
    excerpts = []
    for number, result in enumerate(response.results[:3], 1):
        title = _excerpt(result.title, 140)
        snippet = _excerpt(result.snippet, 280)
        excerpts.append("[%d] %s%s Source: %s" % (
            number, title, ": " + snippet if snippet else "", result.url))
    return "Search results " + label + " (snippets, not independently verified): " + " | ".join(excerpts)


def TAKES_AS_IT_COMES(text, memory=None):
    if in_a_safety_thread(memory):
        return False
    return _capability_question(text) or (enabled() and query_for(text, memory) is not None)


def CLAIMS_INSTEAD(text, memory=None):
    return TAKES_AS_IT_COMES(text, memory)
