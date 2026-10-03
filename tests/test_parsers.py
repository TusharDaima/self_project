"""Parser tests against saved copies of the source pages (captured 23 Sep 2026).

If a site changes its layout, re-save the page into tests/fixtures/ and update the expected values.
"""
import json
from pathlib import Path

from scraper import build, chittorgarh, insights, ipowatch, news
from scraper.merge import names_match

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_ipo_lists():
    sme = chittorgarh.parse_ipo_list(read("chittorgarh_list_sme.html"))
    main = chittorgarh.parse_ipo_list(read("chittorgarh_list_mainboard.html"))
    assert len(sme["open"]) == 10 and len(main["open"]) == 5
    assert {"name": "Robokidz Eduventures",
            "url": "https://www.chittorgarh.com/ipo/robokidz-eduventures-ipo/3205/"} in sme["open"]
    assert any(i["name"] == "Moneyview" for i in main["upcoming"])

    singular = chittorgarh.parse_ipo_list(
        '<p>The upcoming SME IPO in India this week and coming week is '
        '<a href="/ipo/rkfashion-accessories-ipo/3301/" title="R.K.Fashion Accessories IPO">R.K.Fashion Accessories IPO</a>.</p>'
        '<p>There are no upcoming mainboard IPOs.</p>'
        '<p>The current active SME IPO is <a href="/ipo/x-ipo/1/" title="X Ltd IPO">X Ltd IPO</a>.</p>')
    assert [i["name"] for i in singular["upcoming"]] == ["R.K.Fashion Accessories"]
    assert [i["name"] for i in singular["open"]] == ["X Ltd"]


def test_detail_sme():
    d = chittorgarh.parse_detail(read("chittorgarh_detail_sme_subscribed.html"))
    assert d["name"] == "Robokidz Eduventures"
    assert d["type"] == "SME"
    assert (d["open_date"], d["close_date"]) == ("2026-09-21", "2026-09-23")
    assert d["lot_size"] == 1200
    assert d["price_high"] == 106
    assert d["issue_size_cr"] == 31
    assert d["min_application"] == {"label": "Individual investors (IND) (Min)", "lots": 2,
                                    "shares": 2400, "amount": 254400}
    assert d["financials"]["periods"][0] == "31 Mar 2026"
    assert d["financials"]["rows"]["Profit After Tax"] == [10.06, 4.98, 2.42]
    assert d["about"][0].startswith("Incorporated in December 2014")
    assert d["strengths"][0].startswith("Integrated end-to-end")
    assert d["objects"][0]["amount_cr"] == 23.46


def test_detail_mainboard():
    d = chittorgarh.parse_detail(read("chittorgarh_detail_mainboard.html"))
    assert d["name"] == "ArMee Infotech"
    assert d["type"] == "Mainboard"
    assert d["lot_size"] == 40
    assert d["min_application"]["amount"] == 15000
    assert d["issue_size_cr"] == 300


def test_subscription():
    s = chittorgarh.parse_subscription(read("chittorgarh_subscription_sme.html"))
    assert s["total"] == 833.56
    assert s["as_of"] == "Sep 23, 2026 18:54"
    assert {"category": "Retail Individual", "times": 807.12} in s["rows"]


def test_performance_tracker():
    main = chittorgarh.parse_performance(read("chittorgarh_perf_mainboard.html"))
    sme = chittorgarh.parse_performance(read("chittorgarh_perf_sme.html"))
    assert len(main) == 86 and len(sme) == 148
    assert main[0] == {"name": "National Stock Exchange of India Ltd.", "listing_gain_pct": 1.85, "current_gain_pct": 0.43}
    assert {"name": "Kheria Autocomp Ltd.", "listing_gain_pct": 2.03, "current_gain_pct": -1.39} in sme
    # Keys used by the page to match a saved IPO with its listing performance.
    assert build.name_key("National Stock Exchange of India Ltd.") == build.name_key("National Stock Exchange of India")


def test_gmp_table():
    rows = ipowatch.parse_gmp_table(read("ipowatch_gmp.html"))
    assert {r["type"] for r in rows} == {"Mainboard", "SME"}
    robo = next(r for r in rows if r["name"] == "Robokidz Eduventures")
    assert (robo["gmp"], robo["gmp_pct"], robo["est_listing"], robo["status"]) == (65, 61.32, 171, "Open")
    # The past-performance table further down the page must be ignored.
    assert not any(r["name"] == "Manika Plastech" for r in rows)


def test_gmp_table_combined_layout():
    """Layout from Oct 2026: one table, status code and type inside the name cell."""
    rows = ipowatch.parse_gmp_table(read("ipowatch_gmp_combined.html"))
    assert len(rows) == 31
    tna = next(r for r in rows if r["name"] == "TNA Solutions")
    assert (tna["type"], tna["status"], tna["gmp"], tna["gmp_pct"], tna["est_listing"], tna["price"]) == \
        ("SME", "Open", 6, 8.57, 76, 70)
    assert tna["dates"] == "30-6 Oct"
    orient = next(r for r in rows if r["name"] == "Orient Cables")
    assert (orient["type"], orient["status"], orient["gmp"]) == ("Mainboard", "Closed", 123)
    jio = next(r for r in rows if r["name"] == "Jio Platform")
    assert jio["price"] is None and jio["est_listing"] is None and jio["gmp_pct"] is None
    assert jio["url"].startswith("https://")


def test_name_matching():
    assert names_match("German Green Steel", "German Green Steel & Power")
    assert names_match("Acevector", "Acevector (Snapdeal)")
    assert names_match("Shah Investor’s Home", "Shah Investor's Home ;")
    assert names_match("S.K.Offset", "S.K.Offset")
    assert names_match("Sai Urja Indo Ventures", "Sai Urja Indo")
    assert not names_match("Himalayan Solar", "Himalaya Nutravedics")
    assert not names_match("Orient Cables", "Orient Electric")


def test_insights():
    fin = {"periods": ["30 Sep 2026", "31 Mar 2026", "31 Mar 2025", "31 Mar 2024"],
           "rows": {"Total Income": [50, 100, 70, 50], "Profit After Tax": [6, 10, 5, 3]}}
    out = insights.analyse(fin)
    assert "Income +43% YoY" in out["metrics"]
    assert "PAT +100% YoY" in out["metrics"]
    assert any(f["text"].startswith("Strong growth") for f in out["flags"])
    assert any(f["text"] == "Profit up 3 years in a row" for f in out["flags"])
    assert out["partial"].startswith("Period to 30 Sep 2026")

    loss = {"periods": ["31 Mar 2026", "31 Mar 2025"],
            "rows": {"Total Income": [100, 90], "Profit After Tax": [-4, 2]}}
    assert insights.analyse(loss)["flags"][0] == {"tone": "bad", "text": "Loss-making in FY26"}


def test_news_filters():
    items = news.parse_rss(read("google_news.xml"), limit=10, company="Varmora Granito")
    assert items and all("varmora" in i["title"].lower() for i in items)
    assert not any(i["source"] == "IPO Watch" for i in items)
    biz = news.parse_rss(read("google_news.xml"), limit=10, company="Varmora Granito", exclude=news.IPO_CHATTER)
    assert not any("IPO" in i["title"] for i in biz)


def test_ipowatch_fallback_skips_closed():
    from datetime import date
    today = date(2026, 9, 24)
    assert build._ipowatch_close_date("21-23 Sept", today) == date(2026, 9, 23)
    assert build._ipowatch_close_date("30-5 Oct", today) == date(2026, 10, 5)
    rows = [{"name": "Closed Yesterday", "type": "SME", "status": "Open", "dates": "21-23 Sept"},
            {"name": "Still Open", "type": "SME", "status": "Open", "dates": "23-25 Sept",
             "gmp": 1, "gmp_pct": 1.0, "est_listing": 10, "updated": "", "trend": "", "price": 9, "url": None},
            {"name": "Known Elsewhere", "type": "SME", "status": "Open", "dates": "23-25 Sept"}]
    extra = build._ipowatch_only(rows, [{"name": "Known Elsewhere"}], today)
    assert [e["name"] for e in extra] == ["Still Open"]


def test_inr_format():
    assert build.inr(254400) == "2,54,400"
    assert build.inr(15000) == "15,000"
    assert build.inr(999) == "999"
    assert build.inr(1562.5, 1) == "1,562.5"


def test_render_smoke(tmp_path):
    """The template renders with real parsed data and with a GMP-only fallback card."""
    ipo = chittorgarh.parse_detail(read("chittorgarh_detail_sme_subscribed.html"))
    ipo.update(status="open", day_label="Closes today",
               subscription=chittorgarh.parse_subscription(read("chittorgarh_subscription_sme.html")),
               insights=insights.analyse(ipo["financials"], ipo["kpis"], ipo["valuation"]))
    fallback = {"name": "Only On IPOWatch", "type": "SME", "status": "open", "partial_source": True,
                "gmp": {"gmp": 5, "gmp_pct": 5.0}, "insights": insights.analyse(None)}
    ipo["key"] = build.name_key(ipo["name"])
    fallback["key"] = build.name_key(fallback["name"])
    market = {"performance": [{"name": "X </script> Ltd", "key": "x", "listing_gain_pct": 1, "current_gain_pct": 2}],
              "gmp": []}
    html = build.render({"generated_display": "now", "open": [ipo, fallback], "upcoming": [], "warnings": ["x"],
                         "market": market})
    assert "833.56x" in html and "1,200 shares" in html and "₹2,54,400" in html
    assert "Only On IPOWatch" in html
    assert '"key": "robokidz eduventures"' in html and "+ Add to My IPOs" in html
    assert "X </script> Ltd" not in html  # embedded JSON must not be able to close its <script> tag
    json.dumps(ipo, ensure_ascii=False)  # data must stay JSON-serialisable
