"""Match IPO names between sources, which abbreviate differently
(e.g. "German Green Steel" vs "German Green Steel & Power", "Acevector" vs "Acevector (Snapdeal)")."""
import re
from difflib import SequenceMatcher

_DROP = {"ltd", "limited", "ipo", "and", "the", "pvt", "private"}


def tokens(name):
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)          # bracketed aliases
    s = re.sub(r"[.'’`]", "", s)             # S.K.Offset -> skoffset, Investor's -> investors
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return [t for t in s.split() if t not in _DROP]


def names_match(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) >= 2 and long_[: len(short)] == short:
        return True
    return SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() >= 0.85


def find_match(name, candidates, key="name", ipo_type=None):
    """Best candidate whose `key` matches `name` (same IPO type first, if given)."""
    same = [c for c in candidates if ipo_type is None or c.get("type") == ipo_type]
    for c in same + [c for c in candidates if c not in same]:
        if names_match(name, c.get(key)):
            return c
    return None
