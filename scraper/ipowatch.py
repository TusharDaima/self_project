"""Parser for the ipowatch.in grey market premium (GMP) page."""
import re

from bs4 import BeautifulSoup

from .text import clean, to_number

GMP_URL = "https://www.ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"

# Heading text above each table -> IPO type. Other tables (past performance) are ignored.
_TABLE_TYPES = {"mainboard ipo gmp": "Mainboard", "sme ipo gmp": "SME"}


def parse_gmp_table(html):
    """-> list of {name, type, gmp, gmp_pct, est_listing, price, dates, status, updated, trend, url}."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for table in soup.find_all("table"):
        heading = table.find_previous(["h1", "h2", "h3", "h4"])
        ipo_type = _TABLE_TYPES.get(clean(heading.get_text(" ")).lower()) if heading else None
        if not ipo_type:
            continue
        trs = table.find_all("tr")
        header = [clean(c.get_text(" ")).lower() for c in trs[0].find_all(["td", "th"])] if trs else []
        if not header or "ipo gmp" not in " ".join(header):
            continue
        for tr in trs[1:]:
            cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
            if len(cells) < 7:
                continue
            row = dict(zip(header, cells))
            link = tr.find("a", href=True)
            est = row.get("est. listing", "")
            pct = re.search(r"\((-?[\d.]+)%\)", est)
            out.append({
                "name": row.get("ipo name", cells[0]),
                "type": ipo_type,
                "gmp": to_number(row.get("ipo gmp*", row.get("ipo gmp", ""))),
                "gmp_pct": float(pct.group(1)) if pct else None,
                "est_listing": to_number(est),
                "price": to_number(row.get("price band", "")),
                "dates": row.get("date"),
                "status": row.get("status"),
                "updated": row.get("last updated"),
                "trend": row.get("trend"),
                "url": link["href"] if link else None,
            })
    return out
