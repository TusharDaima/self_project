"""Recent headlines about a company from the Google News RSS feed.

Two lookups per company:
  * business news (IPO chatter excluded, last 6 months) - orders, expansions, disputes etc.
  * IPO news (last 30 days) - subscription/GMP coverage
"""
import re
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .merge import tokens
from .text import IST, clean

RSS_URL = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"

# IPO aggregator sites repeat the same listing data we already show; skip them.
SKIP_SOURCES = {"ipo watch", "ipowatch", "chittorgarh.com", "investorgain", "ipo central", "ipoplatform",
                "marketscreener.com", "revelio labs", "tracxn", "zaubacorp"}

# Headlines about the IPO itself; kept out of the "business developments" list.
IPO_CHATTER = re.compile(r"\b(ipos?|initial public offering|gmps?|grey market|subscri\w*|anchor|listings?|allotment|"
                         r"price band|rhp|drhp|primary market|share price)\b", re.I)

POSITIVE = re.compile(
    r"\b(order|orders|contract|wins?|won|winners?|bags?|secures?|acquir\w*|expan\w*|partnership|ties? up|mou|"
    r"collaborat\w*|execut\w*|award\w*|launch\w*|record|capacity|new plant|approval|approved|"
    r"profit (?:jumps|rises|surges))\b", re.I)
NEGATIVE = re.compile(
    r"\b(fir|fraud|raid\w*|penalt\w*|fined?|dispute|probe|notice|default\w*|loss widens|lawsuit|arrest\w*|"
    r"ban(?:ned|s)?|shut\w*|strike)\b", re.I)


def business_url(company, days=180):
    return RSS_URL.format(q=quote_plus(f'"{company}" -IPO -GMP when:{days}d'))


def ipo_url(company, days=30):
    return RSS_URL.format(q=quote_plus(f'"{company}" IPO when:{days}d'))


def _key_term(company):
    """A term that must appear in a headline for it to be about this company."""
    t = tokens(company)
    if not t:
        return ""
    return t[0] if len(t[0]) >= 5 or len(t) == 1 else " ".join(t[:2])


def parse_rss(xml, limit=3, company=None, exclude=None):
    """-> [{title, source, date, link, tone}] newest first, aggregators removed.

    If `company` is given, only headlines mentioning it are kept. Headlines matching the
    `exclude` regex are dropped. Each item gets a tone: "good" (orders, expansion...),
    "bad" (disputes, penalties...) or "".
    """
    soup = BeautifulSoup(xml, "xml")
    must = _key_term(company) if company else ""
    items = []
    for it in soup.find_all("item"):
        source = clean(it.source.get_text()) if it.source else ""
        if source.lower() in SKIP_SOURCES:
            continue
        title = clean(it.title.get_text()) if it.title else ""
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        if must and must not in " ".join(tokens(title)):
            continue
        if exclude and exclude.search(title):
            continue
        try:
            published = parsedate_to_datetime(it.pubDate.get_text()).astimezone(IST)
        except (AttributeError, TypeError, ValueError):
            published = None
        tone = "bad" if NEGATIVE.search(title) else "good" if POSITIVE.search(title) else ""
        items.append({
            "title": title,
            "source": source,
            "date": published.strftime("%d %b %Y") if published else "",
            "_sort": published.timestamp() if published else 0,
            "link": clean(it.link.get_text()) if it.link else "",
            "tone": tone,
        })
    items.sort(key=lambda x: x["_sort"], reverse=True)

    # Drop near-duplicate headlines (same story from several outlets).
    unique, seen = [], []
    for it in items:
        words = set(tokens(it["title"]))
        if any(len(words & s) >= 0.7 * max(1, min(len(words), len(s))) for s in seen):
            continue
        seen.append(words)
        del it["_sort"]
        unique.append(it)
    return unique[:limit]
