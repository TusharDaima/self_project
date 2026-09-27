"""Turn restated financials and KPIs into short, factual signals."""
import re

from .text import to_number

STRONG_GROWTH_PCT = 25


def _pct_change(new, old):
    if new is None or old is None or old <= 0:
        return None
    return (new - old) / old * 100


def _row(fin, *labels):
    for label in labels:
        for key, values in fin["rows"].items():
            if key.lower() == label.lower():
                return values
    return None


def _fy_label(period):
    """'31 Mar 2026' -> 'FY26'."""
    m = re.search(r"(\d{4})$", period)
    return f"FY{m.group(1)[2:]}" if m else period


def analyse(financials, kpis=None, valuation=None):
    """-> {"metrics": [str], "flags": [{"tone": good|bad|warn, "text": str}], "partial": str|None}"""
    out = {"metrics": [], "flags": [], "partial": None}
    if not financials or not financials.get("periods"):
        return out

    periods = financials["periods"]
    income = _row(financials, "Total Income", "Revenue")
    pat = _row(financials, "Profit After Tax", "PAT")
    net_worth = _row(financials, "NET Worth", "Net Worth")
    debt = _row(financials, "Total Borrowing")

    full_years = [i for i, p in enumerate(periods) if p.lower().startswith("31 mar")]
    part_years = [i for i, p in enumerate(periods) if i not in full_years]

    if part_years and income and pat:
        i = part_years[0]
        out["partial"] = (f"Period to {periods[i]}: income ₹{income[i]:,.1f} Cr, PAT ₹{pat[i]:,.1f} Cr "
                          f"(part-year, not compared)")

    if len(full_years) < 1 or not income or not pat:
        return out
    cur = full_years[0]
    label = _fy_label(periods[cur])

    if income[cur] is not None:
        out["metrics"].append(f"{label} income ₹{income[cur]:,.1f} Cr")
    if pat[cur] is not None:
        out["metrics"].append(f"PAT ₹{pat[cur]:,.1f} Cr")
        margin = to_number((kpis or {}).get("PAT Margin"))
        if margin is None and income[cur]:
            margin = pat[cur] / income[cur] * 100
        if margin is not None:
            out["metrics"].append(f"PAT margin {margin:.1f}%")

    if len(full_years) >= 2:
        prev = full_years[1]
        inc_g = _pct_change(income[cur], income[prev])
        pat_g = _pct_change(pat[cur], pat[prev])
        if inc_g is not None:
            out["metrics"].append(f"Income {inc_g:+.0f}% YoY")
        if pat_g is not None:
            out["metrics"].append(f"PAT {pat_g:+.0f}% YoY")

        if pat[cur] is not None and pat[cur] < 0:
            out["flags"].append({"tone": "bad", "text": f"Loss-making in {label}"})
        elif pat[prev] is not None and pat[prev] <= 0 < (pat[cur] or 0):
            out["flags"].append({"tone": "good", "text": f"Turned profitable in {label}"})
        elif inc_g is not None and pat_g is not None and inc_g > STRONG_GROWTH_PCT and pat_g > STRONG_GROWTH_PCT:
            out["flags"].append({"tone": "good", "text": f"Strong growth: income {inc_g:+.0f}%, profit {pat_g:+.0f}%"})
        elif pat_g is not None and pat_g < 0:
            out["flags"].append({"tone": "bad", "text": f"Profit fell {abs(pat_g):.0f}% in {label}"})
        elif inc_g is not None and inc_g < 0:
            out["flags"].append({"tone": "warn", "text": f"Income fell {abs(inc_g):.0f}% in {label}"})

        if len(full_years) >= 3:
            oldest = full_years[2]
            if all(v is not None for v in (pat[cur], pat[prev], pat[oldest])) and pat[cur] > pat[prev] > pat[oldest] > 0:
                out["flags"].append({"tone": "good", "text": "Profit up 3 years in a row"})

        if debt and net_worth and None not in (debt[cur], debt[prev], net_worth[cur]):
            debt_g = _pct_change(debt[cur], debt[prev])
            if debt_g is not None and debt_g > 50 and net_worth[cur] and debt[cur] / net_worth[cur] > 1:
                out["flags"].append({"tone": "warn", "text": f"Borrowing up {debt_g:.0f}% (debt > net worth)"})

    kpis = kpis or {}
    roe = to_number(kpis.get("ROE"))
    if roe is not None and roe >= 20:
        out["flags"].append({"tone": "good", "text": f"High ROE {roe:.0f}%"})
    de = to_number(kpis.get("Debt/Equity"))
    if de is not None and de > 1.5:
        out["flags"].append({"tone": "warn", "text": f"High debt/equity {de:.2f}"})

    pe = (valuation or {}).get("P/E (x)", {}).get("post")
    if to_number(pe):
        out["metrics"].append(f"Post-issue P/E {to_number(pe):.1f}x")
    return out
