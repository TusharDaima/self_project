"""Parser for the ipowatch.in grey market premium (GMP) page."""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .text import clean, to_number

GMP_URL = "https://www.ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"

# Status codes written after the name in the combined table, e.g. "TNA Solutions (O) SME".
_STATUS_CODES = {"U": "Upcoming", "O": "Open", "C": "Closed"}

# Header keyword -> field. Checked in order; the first keyword contained in a header wins.
_COLUMNS = [
    ("last updated", "updated"),
    ("ipo name", "name"),
    ("company", "name"),
    ("gmp", "gmp"),
    ("trend", "trend"),
    ("price band", "price"),
    ("est.", "est"),
    ("date", "dates"),
    ("status", "status"),
]


def _column_map(header):
    cols = {}
    for i, h in enumerate(header):
        for keyword, field in _COLUMNS:
            if keyword in h and field not in cols:
                cols[field] = i
                break
    return cols


def _type_from(text):
    t = text.lower()
    return "SME" if "sme" in t else "Mainboard" if "mainboard" in t else None


def parse_gmp_table(html):
    """-> list of {name, type, gmp, gmp_pct, est_listing, price, dates, status, updated, trend, url}.

    Handles both layouts IPOWatch has used: separate "Mainboard IPO GMP" / "SME IPO GMP" tables
    with a Status column, and one combined "Current IPO GMP" table whose name cell reads
    "<name> (O) SME" (status code + type).
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [clean(c.get_text(" ")).lower() for c in trs[0].find_all(["td", "th"])]
        cols = _column_map(header)
        # Live GMP tables have a price band; the past-performance table ("IPO Price | Listing Price") doesn't.
        if not {"name", "gmp", "price"} <= cols.keys():
            continue
        heading = table.find_previous(["h1", "h2", "h3", "h4"])
        table_type = _type_from(clean(heading.get_text(" "))) if heading else None

        for tr in trs[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < len(cols):
                continue
            text = [clean(c.get_text(" ")) for c in cells]

            def col(field):
                i = cols.get(field)
                return text[i] if i is not None and i < len(text) else ""

            name_cell = cells[cols["name"]]
            link = name_cell.find("a", href=True) or tr.find("a", href=True)
            raw_name = col("name")
            code = re.search(r"\(([UOC])\)", raw_name)
            name = clean(link.get_text(" ")) if link and clean(link.get_text(" ")) else raw_name
            name = clean(re.sub(r"\(([UOC])\)|\b(SME|Mainboard)\b", " ", name))

            est = col("est")
            price = to_number(col("price"))  # "₹-" while the price band isn't announced
            pct = re.search(r"\((-?[\d.]+)%\)", est)
            out.append({
                "name": name,
                "type": table_type or _type_from(raw_name) or "Mainboard",
                "gmp": to_number(col("gmp")),
                "gmp_pct": float(pct.group(1)) if pct and price else None,
                "est_listing": to_number(est.split("(")[0]) if price else None,
                "price": price,
                "dates": col("dates").rstrip("*") or None,
                "status": col("status") or (_STATUS_CODES[code.group(1)] if code else None),
                "updated": col("updated") or None,
                "trend": col("trend") or None,
                "url": urljoin(GMP_URL, link["href"]) if link else None,
            })
    return out
