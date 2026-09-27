"""Parsers for chittorgarh.com: the current/upcoming IPO lists, IPO detail pages and subscription pages."""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .text import clean, parse_long_date, to_int, to_number

BASE = "https://www.chittorgarh.com"
LIST_URLS = {
    "Mainboard": BASE + "/report/ipo-in-india-list-main-board-sme/82/mainboard/",
    "SME": BASE + "/report/ipo-in-india-list-main-board-sme/82/sme/",
}


def _soup(html):
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------- IPO lists

def parse_ipo_list(html):
    """Read the "current active IPOs are ..." and "upcoming IPOs ... are ..." sentences.

    Returns {"open": [{"name", "url"}], "upcoming": [...]}.
    """
    out = {"open": [], "upcoming": []}
    for p in _soup(html).find_all("p"):
        text = clean(p.get_text(" ")).lower()
        if re.search(r"\bactive\b.*\bipos are\b", text[:80]):
            key = "open"
        elif text.startswith("the upcoming") and "ipos" in text:
            key = "upcoming"
        else:
            continue
        for a in p.find_all("a", href=True):
            if "/ipo/" not in a["href"]:
                continue
            name = re.sub(r"\s+IPO$", "", clean(a.get("title") or a.get_text()))
            out[key].append({"name": name, "url": urljoin(BASE, a["href"])})
    return out


# ---------------------------------------------------------------- helpers

def _table_after_heading(soup, heading_substr):
    for table in soup.find_all("table"):
        h = table.find_previous(["h2", "h3"])
        if h and heading_substr.lower() in clean(h.get_text(" ")).lower():
            return table
    return None


def _table_with_row(soup, first_cell):
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if cells and clean(cells[0].get_text(" ")).lower().startswith(first_cell.lower()):
                return table
    return None


def _rows(table):
    return [[clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]


def _kv(table):
    return {r[0]: r[1] for r in _rows(table) if len(r) >= 2 and r[0]} if table else {}


def subscription_url(detail_url):
    return detail_url.replace("/ipo/", "/ipo_subscription/", 1)


# ---------------------------------------------------------------- detail page

def parse_detail(html, url=""):
    soup = _soup(html)
    d = {"chittorgarh_url": url}

    title = clean(soup.title.get_text()) if soup.title else ""
    d["name"] = re.split(r"\s+IPO\b", title)[0] if title else ""

    # Dates: the JSON-LD "Event" block has unambiguous long-form dates.
    m_start = re.search(r'"startDate":"([A-Za-z]+ \d{1,2}, \d{4})"', html)
    m_end = re.search(r'"endDate":"([A-Za-z]+ \d{1,2}, \d{4})"', html)
    start = parse_long_date(m_start.group(1)) if m_start else None
    end = parse_long_date(m_end.group(1)) if m_end else None
    d["open_date"] = start.isoformat() if start else None
    d["close_date"] = end.isoformat() if end else None

    details = _kv(_table_after_heading(soup, "IPO Details"))
    d["ipo_date_text"] = details.get("IPO Date")
    d["listing_date"] = details.get("Listing Date", "").replace(" T", "").strip() or None
    d["face_value"] = details.get("Face Value")
    d["issue_type"] = details.get("Issue Type")
    d["sale_type"] = details.get("Sale Type")
    d["listing_at"] = details.get("Listing At")
    d["type"] = "SME" if "SME" in (d["listing_at"] or "").upper() else "Mainboard"
    d["lot_size"] = to_int(details.get("Lot Size"))

    band = details.get("Price Band") or details.get("Issue Price") or ""
    prices = [to_number(p) for p in re.findall(r"₹\s*[\d,.]+", band)]
    prices = [p for p in prices if p is not None]
    d["price_band"] = band or None
    d["price_high"] = max(prices) if prices else None
    if details.get("Issue Price"):
        d["issue_price"] = to_number(details["Issue Price"])

    size = _kv(_table_with_row(soup, "Total Issue Size")).get("Total Issue Size", "")
    m = re.search(r"₹\s*([\d,.]+)\s*Cr", size)
    d["issue_size_cr"] = to_number(m.group(1)) if m else None

    d["min_application"] = _parse_lot_table(_table_after_heading(soup, "Lot Size"))
    d["financials"] = _parse_financials(_table_after_heading(soup, "Financials"))
    d["objects"] = _parse_objects(_table_after_heading(soup, "Objects of the Issue"))
    d["kpis"] = _parse_kpis(_table_after_heading(soup, "Key Performance Indicator"))
    d["valuation"] = _parse_valuation(_table_after_heading(soup, "IPO Valuation"))
    d["reviews"] = _parse_reviews(_table_after_heading(soup, "Recommendations"))
    d.update(_parse_about(soup))
    return d


def _parse_lot_table(table):
    """First row after the header = the minimum application for an individual investor."""
    if not table:
        return None
    for r in _rows(table)[1:]:
        if len(r) >= 4 and to_int(r[2]):
            return {"label": r[0], "lots": to_int(r[1]), "shares": to_int(r[2]), "amount": to_number(r[3])}
    return None


def _parse_financials(table):
    """-> {"periods": ["31 Mar 2026", ...], "rows": {"Total Income": [..], ...}, "unit": "..."}"""
    if not table:
        return None
    rows = _rows(table)
    if not rows or not rows[0] or rows[0][0].lower() != "period ended":
        return None
    periods = rows[0][1:]
    data, unit = {}, None
    for r in rows[1:]:
        if len(r) == 1:
            unit = r[0]
            continue
        data[r[0]] = [to_number(v) for v in r[1:1 + len(periods)]]
    return {"periods": periods, "rows": data, "unit": unit or "Amount in ₹ Crore"}


def _parse_objects(table):
    if not table:
        return []
    out = []
    for r in _rows(table)[1:]:
        if len(r) < 2 or r[1].lower() == "total" or not r[1]:
            continue
        out.append({"object": r[1], "amount_cr": to_number(r[2]) if len(r) > 2 else None})
    return out


def _parse_kpis(table):
    if not table:
        return {}
    rows = _rows(table)
    return {r[0]: r[1] for r in rows[1:] if len(r) >= 2 and r[1]}


def _parse_valuation(table):
    if not table:
        return {}
    return {r[0]: {"pre": r[1] if len(r) > 1 else "", "post": r[2] if len(r) > 2 else ""}
            for r in _rows(table)[1:] if r}


def _parse_reviews(table):
    """Broker recommendation counts, e.g. {"Subscribe": 2, "May Apply": 1, ...}."""
    if not table:
        return None
    rows = _rows(table)
    header = rows[0][1:] if rows else []
    for r in rows[1:]:
        if r and r[0].lower().startswith("broker"):
            return {h: to_int(v) or 0 for h, v in zip(header, r[1:])}
    return None


def _parse_about(soup):
    """About paragraphs plus bulleted sections such as "Strengths" / "Weaknesses"."""
    section = soup.find(id="about-company-section")
    if not section:
        return {"legal_name": None, "about": [], "about_lists": {}}
    heading = section.find("h2")
    legal = clean(heading.get_text(" ")) if heading else ""
    legal = re.sub(r"^About\s+", "", legal)
    body = section.find(id="ipoSummary") or section
    paras, lists, current = [], {}, None
    for el in body.find_all(["p", "ul", "ol"], recursive=False):
        text = clean(el.get_text(" "))
        if not text:
            continue
        if el.name == "p":
            strong = el.find("strong")
            if strong and clean(strong.get_text(" ")) == text and len(text) < 40:
                current = text.rstrip(":")
                continue
            if current is None:
                paras.append(text)
        elif current:
            lists.setdefault(current, []).extend(clean(li.get_text(" ")) for li in el.find_all("li"))
    # The heading varies: "Strengths", "Key Strength", "Competitive Strengths"...
    strengths = next((items for title, items in lists.items() if "strength" in title.lower()), [])
    return {"legal_name": legal or None, "about": paras, "about_lists": lists, "strengths": strengths}


# ---------------------------------------------------------------- subscription page

def parse_subscription(html):
    """-> {"as_of": "Sep 23, 2026 18:54", "rows": [{"category", "times"}], "total": float} or None."""
    soup = _soup(html)
    table = None
    for t in soup.find_all("table"):
        rows = _rows(t)
        if rows and len(rows[0]) >= 2 and "subscription (times)" in rows[0][1].lower():
            table = t
            break
    if not table:
        return None
    rows, total = [], None
    for r in _rows(table)[1:]:
        if len(r) < 2:
            continue
        times = to_number(r[1])
        if r[0].lower().startswith("total"):
            total = times
        else:
            rows.append({"category": r[0], "times": times})
    m = re.search(r"subscribed\s+[\d.,]+x\s+(?:times\s+)?as of\s+([A-Za-z]{3} \d{1,2}, \d{4}(?: \d{1,2}:\d{2})?)",
                  clean(soup.get_text(" ")))
    return {"as_of": m.group(1) if m else None, "rows": rows, "total": total}
