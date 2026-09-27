"""Small helpers for cleaning scraped text and numbers."""
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def clean(s):
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", s or "").strip()


def to_number(s):
    """First number in a string ('₹1,95,000' -> 195000.0, '-12.5%' -> -12.5). None if absent."""
    if s is None:
        return None
    s = str(s).replace("−", "-")  # unicode minus
    m = _NUM_RE.search(s)
    if not m:
        return None
    val = float(m.group(0).replace(",", ""))
    # Handle a sign placed before the currency symbol, e.g. "-₹5".
    if val > 0 and re.search(r"-\s*₹\s*" + re.escape(m.group(0)), s):
        val = -val
    return val


def to_int(s):
    n = to_number(s)
    return int(n) if n is not None else None


def parse_long_date(s):
    """'September 21, 2026' or 'Monday, September 21, 2026' -> date. None if unparseable."""
    s = clean(s)
    s = re.sub(r"^[A-Za-z]+day,\s*", "", s)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def today_ist():
    return datetime.now(IST).date()


def now_ist():
    return datetime.now(IST)
