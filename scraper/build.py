"""Entry point: scrape all sources, merge, and write docs/data.json + docs/index.html.

    python -m scraper.build            # full run
    python -m scraper.build --no-news  # skip Google News (faster while testing)
"""
import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from . import chittorgarh, insights, ipowatch, news
from .fetch import get_text
from .merge import find_match, names_match, tokens
from .text import now_ist, today_ist

log = logging.getLogger("build")
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs"
TEMPLATE_DIR = ROOT / "templates"


class Run:
    """Collects warnings and gives access to the previous run's data for fallbacks."""

    def __init__(self, previous):
        self.previous = previous or {}
        self.warnings = []

    def warn(self, msg):
        log.warning(msg)
        self.warnings.append(msg)

    def previous_ipo(self, name):
        for section in ("open", "upcoming"):
            for ipo in self.previous.get(section, []):
                if names_match(name, ipo.get("name")):
                    return ipo
        return None


def _why(e):
    """Short, page-friendly reason for a failure."""
    resp = getattr(e, "response", None)
    if resp is not None:
        return f"HTTP {resp.status_code}"
    if isinstance(e, ValueError):
        return str(e)
    return type(e).__name__


def _load_previous(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def discover(run):
    """IPO names/URLs from Chittorgarh's Mainboard and SME list pages."""
    found = []
    for ipo_type, url in chittorgarh.LIST_URLS.items():
        try:
            lists = chittorgarh.parse_ipo_list(get_text(url))
        except Exception as e:  # noqa: BLE001 - one failed source must not stop the run
            run.warn(f"Could not load Chittorgarh {ipo_type} list: {_why(e)}")
            continue
        if not lists["open"] and not lists["upcoming"]:
            run.warn(f"Chittorgarh {ipo_type} list page had no IPO links (layout change?)")
        for status, items in lists.items():
            for item in items:
                if not any(f["url"] == item["url"] for f in found):
                    found.append({**item, "type": ipo_type, "list_status": status})
    return found


def load_gmp(run):
    try:
        rows = ipowatch.parse_gmp_table(get_text(ipowatch.GMP_URL))
        if not rows:
            raise ValueError("no GMP rows found (layout change?)")
        return rows, False
    except Exception as e:  # noqa: BLE001
        run.warn(f"Could not load IPOWatch GMP: {_why(e)}. Showing last known GMP values.")
        return [], True


def _status(ipo, today, fallback):
    try:
        start = date.fromisoformat(ipo["open_date"])
        end = date.fromisoformat(ipo["close_date"])
    except (TypeError, ValueError, KeyError):
        return fallback
    if start <= today <= end:
        return "open"
    if today < start:
        return "upcoming"
    return "closed"


def _day_label(ipo, today):
    try:
        if ipo["status"] == "open":
            n = (date.fromisoformat(ipo["close_date"]) - today).days
            return "Closes today" if n == 0 else "Closes tomorrow" if n == 1 else f"Closes in {n} days"
        n = (date.fromisoformat(ipo["open_date"]) - today).days
        return "Opens tomorrow" if n == 1 else f"Opens in {n} days"
    except (TypeError, ValueError, KeyError):
        return ""


def _attach_gmp(ipo, gmp_rows, gmp_stale, run):
    match = find_match(ipo["name"], gmp_rows, ipo_type=ipo.get("type"))
    if match:
        ipo["gmp"] = {k: match[k] for k in ("gmp", "gmp_pct", "est_listing", "updated", "trend")}
        ipo["ipowatch_url"] = match.get("url")
        match["_used"] = True
    elif gmp_stale:
        prev = run.previous_ipo(ipo["name"])
        if prev and prev.get("gmp"):
            ipo["gmp"] = {**prev["gmp"], "stale": True}
            ipo["ipowatch_url"] = prev.get("ipowatch_url")


def build_ipo(item, gmp_rows, gmp_stale, run, today, with_news):
    try:
        ipo = chittorgarh.parse_detail(get_text(item["url"]), item["url"])
    except Exception as e:  # noqa: BLE001
        prev = run.previous_ipo(item["name"])
        run.warn(f"{item['name']}: detail page failed ({_why(e)}); "
                 + ("using previous data" if prev else "showing name only"))
        ipo = {**prev, "stale": True} if prev else {"name": item["name"], "chittorgarh_url": item["url"]}

    ipo["name"] = ipo.get("name") or item["name"]
    ipo["type"] = item["type"]
    ipo["status"] = _status(ipo, today, item["list_status"])
    if ipo["status"] == "closed":
        return None
    ipo["day_label"] = _day_label(ipo, today)

    if ipo["status"] == "open":
        try:
            ipo["subscription"] = chittorgarh.parse_subscription(
                get_text(chittorgarh.subscription_url(item["url"])))
        except Exception as e:  # noqa: BLE001
            prev = run.previous_ipo(ipo["name"])
            run.warn(f"{ipo['name']}: subscription page failed ({_why(e)})")
            if prev and prev.get("subscription"):
                ipo["subscription"] = {**prev["subscription"], "stale": True}

    _attach_gmp(ipo, gmp_rows, gmp_stale, run)
    ipo["insights"] = insights.analyse(ipo.get("financials"), ipo.get("kpis"), ipo.get("valuation"))

    if with_news:
        query = (ipo.get("legal_name") or ipo["name"]).replace(" Ltd.", "").replace(" Limited", "").rstrip(".")
        prev = run.previous_ipo(ipo["name"]) or {}
        lookups = (("business_news", news.business_url(query), 4, news.IPO_CHATTER),
                   ("news", news.ipo_url(query), 3, None))
        for key, url, limit, exclude in lookups:
            try:
                ipo[key] = news.parse_rss(get_text(url), limit=limit, company=query, exclude=exclude)
            except Exception as e:  # noqa: BLE001
                run.warn(f"{ipo['name']}: news fetch failed ({_why(e)})")
                ipo[key] = prev.get(key, [])
    return ipo


def _ipowatch_close_date(dates, today):
    """'21-23 Sept' / '30-5 Oct' -> date of the closing day (current year). None if unparseable."""
    m = re.search(r"-\s*(\d{1,2})\s+([A-Za-z]{3})", dates or "")
    if not m:
        return None
    try:
        close = datetime.strptime(f"{m.group(1)} {m.group(2).title()} {today.year}", "%d %b %Y").date()
    except ValueError:
        return None
    if close < today - timedelta(days=180):  # e.g. "29-2 Jan" seen in late December
        close = close.replace(year=today.year + 1)
    return close


def _ipowatch_only(gmp_rows, known, today):
    """Open IPOs listed on IPOWatch that Chittorgarh didn't give us: show them with GMP data only."""
    extra = []
    for row in gmp_rows:
        if row.get("_used") or (row.get("status") or "").lower() != "open":
            continue
        if any(names_match(row["name"], k["name"]) for k in known):
            continue
        close = _ipowatch_close_date(row.get("dates"), today)
        if close is None or close < today:  # IPOWatch's status can lag a day behind
            continue
        extra.append({
            "name": row["name"], "type": row["type"], "status": "open", "day_label": row.get("dates") or "",
            "price_band": f"₹{row['price']:,.0f}" if row.get("price") else None, "price_high": row.get("price"),
            "gmp": {k: row[k] for k in ("gmp", "gmp_pct", "est_listing", "updated", "trend")},
            "ipowatch_url": row.get("url"), "insights": insights.analyse(None), "partial_source": True,
        })
    return extra


def _sort_key(ipo):
    pct = (ipo.get("gmp") or {}).get("gmp_pct") or 0
    date_key = ipo.get("close_date") if ipo.get("status") == "open" else ipo.get("open_date")
    return (date_key or "9999", -pct)


def collect(run, with_news=True):
    today = today_ist()
    gmp_rows, gmp_stale = load_gmp(run)
    listed = discover(run)

    ipos = []
    if listed:
        for item in listed:
            log.info("IPO: %s (%s)", item["name"], item["type"])
            ipo = build_ipo(item, gmp_rows, gmp_stale, run, today, with_news)
            if ipo:
                ipos.append(ipo)
    elif run.previous:
        run.warn("Chittorgarh unavailable: showing the previous day's IPO list.")
        for section in ("open", "upcoming"):
            for prev in run.previous.get(section, []):
                ipo = {**prev, "stale": True}
                ipo["status"] = _status(ipo, today, section)
                if ipo["status"] != "closed":
                    ipo["day_label"] = _day_label(ipo, today)
                    _attach_gmp(ipo, gmp_rows, gmp_stale, run)
                    ipos.append(ipo)

    # `listed` also holds IPOs we dropped as closed, so they aren't re-added from IPOWatch.
    ipos += _ipowatch_only(gmp_rows, ipos + listed, today)
    for row in gmp_rows:
        row.pop("_used", None)
    for ipo in ipos:
        ipo["key"] = name_key(ipo["name"])

    return {
        "generated_at": now_ist().isoformat(timespec="seconds"),
        "generated_display": now_ist().strftime("%d %b %Y, %I:%M %p IST"),
        "open": sorted([i for i in ipos if i["status"] == "open"], key=_sort_key),
        "upcoming": sorted([i for i in ipos if i["status"] == "upcoming"], key=_sort_key),
        "market": market_data(run, gmp_rows, gmp_stale),
        "warnings": run.warnings,
    }


def name_key(name):
    """Normalised name used by the page's script to match "My IPOs" entries across sources."""
    return " ".join(tokens(name))


def load_performance(run):
    """Listing-day and current gain % of IPOs listed this year, from Chittorgarh's tracker."""
    rows = []
    for ipo_type, url in chittorgarh.PERF_URLS.items():
        try:
            found = chittorgarh.parse_performance(get_text(url))
            if not found:
                raise ValueError("no rows found (layout change?)")
        except Exception as e:  # noqa: BLE001
            run.warn(f"Could not load Chittorgarh {ipo_type} performance tracker: {_why(e)}")
            prev = (run.previous.get("market") or {}).get("performance", [])
            found = [r for r in prev if r.get("type") == ipo_type]
        rows += [{**r, "type": ipo_type, "key": name_key(r["name"])} for r in found]
    return rows


def market_data(run, gmp_rows, gmp_stale):
    """Data the "My IPOs" tab needs for IPOs that have closed or listed."""
    if gmp_stale:
        gmp = (run.previous.get("market") or {}).get("gmp", [])
    else:
        gmp = [{"key": name_key(r["name"]), "name": r["name"], "type": r["type"], "gmp": r["gmp"],
                "gmp_pct": r["gmp_pct"], "status": r["status"], "updated": r["updated"]} for r in gmp_rows]
    return {"performance": load_performance(run), "gmp": gmp}


# ---------------------------------------------------------------- rendering

def inr(value, decimals=0):
    """Indian digit grouping: 195000 -> '1,95,000'."""
    if value is None:
        return "—"
    neg = value < 0
    value = abs(value)
    whole, _, frac = f"{value:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + whole + ("." + frac if frac else "")


def sentences(text, n=3):
    """First n sentences of a paragraph."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text or "")
    return " ".join(parts[:n])


def render(data):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters["inr"] = inr
    env.filters["sentences"] = sentences
    env.tests["search"] = lambda value, pattern: bool(re.search(pattern, value or ""))
    return env.get_template("index.html.j2").render(**data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-news", action="store_true", help="skip Google News lookups")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output folder (default: docs/)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.out.mkdir(parents=True, exist_ok=True)
    data_path = args.out / "data.json"

    run = Run(_load_previous(data_path))
    data = collect(run, with_news=not args.no_news)

    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "index.html").write_text(render(data), encoding="utf-8")
    log.info("Wrote %d open and %d upcoming IPOs to %s (%d warnings)",
             len(data["open"]), len(data["upcoming"]), args.out, len(data["warnings"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
