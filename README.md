# IPO Watchlist

A static web page that rebuilds every morning at 08:00 IST. It lists the Indian IPOs (Mainboard and SME) that are open for application, plus those opening soon.

For each IPO the page shows:

- lot size and minimum investment
- issue size
- GMP
- live subscription, broken down by category
- what the company does
- financial signals: growth, margins, flags and uses of the money raised
- recent business news, plus IPO news

**Data sources:**

- [chittorgarh.com](https://www.chittorgarh.com): IPO list, details, financials, subscription
- [ipowatch.in](https://www.ipowatch.in): GMP
- Google News RSS: headlines

## My IPOs tab

1. When you apply for an IPO, tap **+ Add to My IPOs** on its card. It appears under **My IPOs → Awaiting allotment**.
2. When allotment is out, tap **Allotted** or **Not allotted**. Not allotted removes the IPO; an **Undo** appears for a few seconds.
3. For allotted IPOs you can change **Lots allotted**. The gain is worked out from your invested amount (issue price × shares):
   - **Listed:** listing-day and current gain %, from chittorgarh.com's IPO performance tracker as of the last update.
   - **Closed but not listed yet:** the expected gain from the latest GMP (unofficial).

The list lives in your browser's local storage. It isn't uploaded anywhere, it won't show up on your other devices, and clearing browser data erases it.

## Run locally

```
pip install -r requirements.txt
python -m scraper.build            # writes docs/index.html and docs/data.json
python -m scraper.build --no-news  # faster, skips Google News
python -m pytest -q                # parser tests against saved pages in tests/fixtures/
```

Open `docs/index.html` in a browser.

## Publish on GitHub Pages (one-time)

1. Create an empty repository on GitHub, then push this folder:
   ```
   git init -b main
   git add .
   git commit -m "IPO watchlist"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. In the repo, go to **Settings → Pages**. Under **Build and deployment**, choose *Deploy from a branch*. Pick `main`, folder `/docs`, then Save.
3. Go to **Settings → Actions → General → Workflow permissions** and choose *Read and write permissions*.
4. On the **Actions** tab, open **Daily IPO update** and click **Run workflow** once. The page will be at `https://<you>.github.io/<repo>/`.

After that, `.github/workflows/daily.yml` runs every day at 08:00 IST (GitHub sometimes starts it a few minutes late). It commits the refreshed `docs/`.

## When a source fails

- **One IPO fails:** only that IPO's fields go blank or fall back to yesterday's values. They're marked "stale" or "last known".
- **A whole site is down:** the page is still built from the last `docs/data.json`, with a warning banner at the top.
- **A site changes its layout:** save the new page into `tests/fixtures/`, run `pytest`, and adjust the parser in `scraper/chittorgarh.py` or `scraper/ipowatch.py`.

## Layout

| Path | Purpose |
|---|---|
| `scraper/chittorgarh.py` | IPO lists, detail pages, subscription pages |
| `scraper/ipowatch.py` | GMP tables (Mainboard + SME) |
| `scraper/news.py` | Google News lookups and positive/negative tagging |
| `scraper/insights.py` | Financial growth signals and flags |
| `scraper/merge.py` | Matching IPO names across sites |
| `scraper/build.py` | Entry point: collect → `docs/data.json` → `docs/index.html` |
| `templates/index.html.j2` | Page template (no external CSS/JS) |

GMP is unofficial. This page is for information only and is not investment advice.
