# Shop Ledger

A personal TikTok Shop product database. It snapshots the top movers every day, computes revenue per SKU instead of guessing from a price range, links every driving video, and tells you plainly when it cannot explain a day's sales.

Zero dependencies. One SQLite file. A six-screen dashboard that runs from disk or a local server.

```
git clone https://github.com/hudsonhild/shop-ledger && cd shop-ledger
cp .env.example .env          # add a free ScrapeCreators key
pip install -e .
shop-ledger run --open
```

## Why this exists

Kalodata, FastMoss and EchoTik all estimate TikTok Shop performance from public signals. None of them hold official TikTok sales data, which is why sellers keep posting that the numbers do not match their own dashboards.

Shop Ledger does not solve that. It does something more useful: it separates the figures that are **exact** from the figures that are **modelled**, and it refuses to spread a number across a gap where the data is not there.

- **Exact**, read straight from the API: lifetime units sold, per-SKU stock, per-SKU price, every related video with its URL, play count, like count and commission flag.
- **Modelled**, derived and carrying error: daily units, daily revenue, and which video drove which sale.
- **Not obtainable**, never invented: ad spend, margin, and any sale the video panel cannot account for. Those are reported as unattributed.

That last one is the whole point. If a product sold 3,000 units and its videos barely moved, the sales came from ads, search or LIVE. Assigning them to whichever video happened to tick up is how the paid tools end up wrong.

## What you get

- A daily snapshot of 50 to 100 products, ranked by **movement** rather than lifetime volume.
- Revenue computed as the sum of `units per variant × price of that variant`. On a product listed at `$18.70 - 55.50`, a midpoint estimate is off by a lot; this is not.
- The top 10 videos each day with real links, creator handles, view deltas and attribution share.
- A confidence figure on every row, and an unattributed residual that is allowed to be large.
- Six screens that work opened from disk or served locally, with no build step, and follow your system light or dark theme.

## Quick start

You need Python 3.11 or newer and a free [ScrapeCreators](https://scrapecreators.com) key, which comes with 10,000 calls and does not ask for a card.

1. `cp .env.example .env` and paste your key into `SCRAPECREATORS_API_KEY`.
2. `pip install -e .`
3. `shop-ledger run` — sweeps, pulls, resolves and renders.
4. Run it again tomorrow. **The first run cannot produce a single number**, because a delta needs two readings. This is normal and the dashboard says so.

Then open `data/out/index.html`, or run `shop-ledger serve --open`.

## Commands

- `shop-ledger init` — create the database.
- `shop-ledger sweep` — search the keyword list, record what is out there, promote the movers into the tracked panel.
- `shop-ledger pull` — full detail pull for the tracked panel. This is where SKU stock and the video panel arrive.
- `shop-ledger resolve` — compute units, revenue and attribution. Pure local work, costs nothing, safe to re-run.
- `shop-ledger render --open` — write the whole site and open it.
- `shop-ledger serve --open` — serve it at `http://127.0.0.1:8787`.
- `shop-ledger run` — sweep, pull, resolve and render in order.
- `shop-ledger status` — what is currently in the database.

## Screens

- **Today** — the metric strip and chart, top movers, top 10 videos, and a data-health strip. Click a metric to re-plot the chart.
- **Products** — the whole tracked panel as a sortable, filterable table. Every row opens a detail page.
- **Product detail** — that product's own chart, its variants with exact per-variant stock and price, its facts including the sold-versus-stock disagreement, and its videos ranked by view delta.
- **Videos** — every video on the panel, commission-flagged or organic, with view deltas, attribution shares and links out to TikTok.
- **Creators** — affiliates aggregated across products, ranked by attributed revenue. A creator appearing on several products is the stronger signal.
- **Data health** — flagged rows, the sold-versus-stock gaps, and the run log.

## What it costs

Each API call is one credit.

- The keyword sweep costs one credit per keyword. The default list has 20.
- The detail pull costs one credit per tracked product per day.
- At a 50-product panel that is about 70 credits a day, so the free 10,000 lasts roughly **140 days**.
- At 100 products it is about 120 a day, roughly 80 days.

Start at 50. A smaller panel with clean history beats a larger one with noisy history, and you can widen it once you trust the series.

Edit `src/shopledger/keywords.txt` or pass `--keywords my-list.txt`. Trim it to the categories you actually sell in.

## Configuration

Everything is read from `.env` or the environment. See `.env.example` for the full list.

- `SCRAPECREATORS_API_KEY` — required.
- `SHOPLEDGER_DATA_DIR` — where the database and dashboard live. Defaults to `./data`.
- `SHOPLEDGER_PANEL_SIZE` — how many products get the daily detail pull. Defaults to 50.
- `SHOPLEDGER_MIN_CREDITS` — abort the run below this balance rather than write a partial day. Defaults to 200.
- `SHOPLEDGER_DEFAULT_VPU` — views per unit sold, used only to bootstrap confidence before a product has its own history.
- `SHOPLEDGER_ENGAGEMENT_K` — how strongly a good like rate outweighs raw reach in attribution. Set to 0 to split purely by views.
- `SHOPLEDGER_PANEL_WINDOW_DAYS` — how long a video that fell out of a product's top 18 keeps being sampled. Defaults to 14.
- `SHOPLEDGER_PANEL_BUDGET` — cap on those re-samples per day, so a long tail of orphans cannot eat tomorrow's credits. Defaults to 25.

Your key is read at runtime and is never written to the database or the dashboard.

## Run it daily

Pick a fixed hour and keep it. A job that drifts from 02:00 to 04:00 turns a 24-hour reading into a 26-hour one and corrupts every rate derived from it.

`scripts/daily.sh` does the whole run and wraps it in `caffeinate`, because a macOS dark-wake can otherwise kill a long network job halfway and leave a partial day.

**macOS and Linux**, via `crontab -e`:

```
0 2 * * * /path/to/shop-ledger/scripts/daily.sh >> /path/to/shop-ledger/data/logs/daily.log 2>&1
```

**macOS with launchd** is steadier than cron for a laptop that sleeps. There is a working plist in `docs/launchd.plist`; keep its log paths out of any cloud-synced folder, since launchd fails with exit 78 when it cannot write them.

**Windows**, via Task Scheduler: a daily task running `shop-ledger run` with the repo as the working directory.

## Reach it from anywhere

The render output is a plain static site, so any static host works and none of them need a build step.

Set `SHOPLEDGER_DEPLOY=1` and `scripts/daily.sh` will publish through the Vercel CLI after each run, if you have it installed and the project linked:

```
cd data/out && vercel deploy --prod
```

GitHub Pages, Netlify, Cloudflare Pages or `rsync` to any web root work the same way: point them at `data/out`. Anything you publish is public unless you add protection at the host, and the pages carry product research rather than anything private, but that is worth a thought before you share the link.

## How it decides the numbers

**Two unit counts, reconciled.** You get sales two ways: the lifetime `sold_count` delta and the summed per-SKU stock delta. Each fails differently, so both run every day.

- They agree within tolerance, so the figure is recorded as exact.
- Stock went up, meaning a restock landed and the stock delta is meaningless for the day. Falls back to the sold counter and flags the row.
- They disagree beyond tolerance. Takes the conservative figure and keeps **both** numbers on the row so the gap stays auditable months later.
- Both flat while the product is live. A genuine zero-sales day, kept in the series rather than dropped.

**Attribution.** For each product, affiliate-flagged videos are weighted by view delta and like rate, then given a share of the day's units. A coverage coefficient decides how much of the day the panel can plausibly explain, and whatever is left over stays unattributed. Confidence below 0.3 means the panel does not explain the sales, and the dashboard says so instead of picking a winner.

**The video panel only grows.** A video that drops out of a product's top 18 keeps being sampled directly for two weeks. Without that, a video slipping to 19th reads identically to a video that stopped existing, and the attribution history breaks silently.

**Raw responses are kept.** Every snapshot stores its full JSON, so a change to the model can be replayed across your entire history without spending a credit refetching.

## Known limits

- **US TikTok Shop only.** The product detail endpoint returns nothing for other regions. Those products are skipped and cost nothing.
- **18 videos per product.** The related-videos list is ranked and truncated, so a video that slips to 19th disappears from the response. Shop Ledger keeps sampling those orphans directly for `SHOPLEDGER_PANEL_WINDOW_DAYS`, so the panel only ever grows, but the initial discovery of a video still depends on it reaching a product's top 18 at least once.
- **Sold-out products look dead.** A product that has run out stops selling, which reads identically to a product nobody wants. Check stock before writing one off.
- **Signed media URLs expire.** Thumbnails are re-resolved each render and fall back to a placeholder. Video links are the durable page URLs and do not expire.
- **Attribution is an inference.** It will never be exact, and the design goal is that it is honest about that rather than confident and wrong.

## Terms of service

This reads publicly visible TikTok Shop data through a third-party API. That runs against TikTok's terms of service. It is built for personal product research and is not affiliated with, endorsed by, or connected to TikTok, ByteDance, Kalodata, FastMoss or EchoTik. You are responsible for how you use it.

## Design

The dashboard copies [ElevenLabs](https://elevenlabs.io)' app surface: their palette, their 14/20 Inter type scale, hairlines instead of shadows, greyed icons that only darken on the active row, and colour confined to the chart ramp and status pills. Icons are drawn on their measured grid — `viewBox="0 0 18 18"`, `stroke-width="1.5"`, round caps and joins, `currentColor` — in `src/shopledger/icons.py`.

The whole dashboard is one template at `src/shopledger/templates/dashboard.html` with `__TOKEN__` placeholders. There is no build step and no framework, so restyling it means editing one file.

## Development

```
pip install -e .
python -m unittest discover -s tests -v
ruff check . && ruff format --check .
```

The reconciliation and attribution rules are the product, so they are covered by tests that pin the behaviour, including the case where attribution must not exceed the day's actual units.

## Licence

MIT. See [LICENSE](LICENSE).
