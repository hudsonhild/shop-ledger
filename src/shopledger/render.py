"""Render the whole dashboard as a static site.

Six screens, no framework and no build step. Every page is the same shell from
`templates/base.html` with `__TOKEN__` placeholders, so restyling means editing
one file. Pages link relatively, so the site works opened from disk or served.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from importlib import resources
from pathlib import Path

from .icons import icon, wordmark
from .ui import (
    SORT_SCRIPT,
    confidence_badge,
    empty,
    esc,
    exact,
    money,
    nav,
    product_row,
    short,
    sortable_table,
    thumb,
    video_row,
)

WINDOW_DAYS = 7
METRICS = [
    ("units", "Units sold", "count"),
    ("revenue", "Revenue", "money"),
    ("tracked", "Tracked products", "count"),
    ("attributed", "Attributed", "percent"),
    ("entrants", "New entrants", "count"),
]
PRODUCT_METRICS = [("units", "Units sold", "count"), ("revenue", "Revenue", "money")]


# --------------------------------------------------------------------- queries


def _days(conn: sqlite3.Connection, limit: int = WINDOW_DAYS) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT day FROM daily_result ORDER BY day DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r["day"] for r in reversed(rows)]


def _series(conn: sqlite3.Connection, days: list[str]) -> dict:
    out = {key: {"values": [], "money": kind == "money"} for key, _, kind in METRICS}
    for day in days:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(units),0) AS units,
                   COALESCE(SUM(revenue),0) AS revenue,
                   COUNT(*) AS tracked,
                   COALESCE(SUM(unattributed),0) AS unattributed
            FROM daily_result WHERE day = ?
            """,
            (day,),
        ).fetchone()
        entrants = conn.execute(
            "SELECT COUNT(*) AS n FROM product WHERE substr(first_seen,1,10) = ?", (day,)
        ).fetchone()["n"]

        units = row["units"] or 0
        out["units"]["values"].append(units)
        out["revenue"]["values"].append(round(row["revenue"] or 0, 2))
        out["tracked"]["values"].append(row["tracked"] or 0)
        attributed = (1 - (row["unattributed"] / units)) * 100 if units else 0
        out["attributed"]["values"].append(round(max(0.0, attributed), 1))
        out["entrants"]["values"].append(entrants)
    return out


def _empty_series(metrics) -> dict:
    return {key: {"values": [], "money": kind == "money"} for key, _, kind in metrics}


def _product_series(conn: sqlite3.Connection, product_id: str, days: list[str]) -> dict:
    out = _empty_series(PRODUCT_METRICS)
    for day in days:
        row = conn.execute(
            "SELECT units, revenue FROM daily_result WHERE product_id = ? AND day = ?",
            (product_id, day),
        ).fetchone()
        out["units"]["values"].append(row["units"] if row else 0)
        out["revenue"]["values"].append(round(row["revenue"], 2) if row else 0)
    return out


# ------------------------------------------------------------------ components


def _strip(series: dict, metrics) -> str:
    cells = []
    for index, (key, label, kind) in enumerate(metrics):
        values = series.get(key, {}).get("values") or []
        if not values:
            value = "---"
        elif kind == "money":
            value = money(values[-1])
        elif kind == "percent":
            value = f"{values[-1]:.0f}<small>%</small>"
        else:
            value = short(values[-1])
        pressed = "true" if index == 0 else "false"
        cells.append(
            f'<button class="cell" type="button" data-key="{key}" aria-pressed="{pressed}">'
            f'<div class="lab">{esc(label)}</div><div class="val">{value}</div></button>'
        )
    return "".join(cells)


def _chart_card(series: dict, days: list[str], metrics) -> str:
    first = days[0] if days else ""
    last = days[-1] if days else ""
    return (
        f'<div class="card"><div class="strip" role="group" '
        f'aria-label="Choose a metric to plot">{_strip(series, metrics)}</div>'
        f'<div class="plot"><svg id="plot" viewBox="0 0 760 170" preserveAspectRatio="none" '
        f'role="img" aria-label="Daily series for the selected metric"></svg>'
        f'<div class="axis"><span>{esc(first)}</span><span>{esc(last)}</span></div></div></div>'
    )


def _chart_script(series: dict) -> str:
    body = resources.files("shopledger.templates").joinpath("chart.js").read_text(encoding="utf-8")
    return f"<script>var SERIES = {json.dumps(series, separators=(',', ':'))};</script>{body}"


# ----------------------------------------------------------------------- shell


class Site:
    """Shared chrome and the facts every page needs."""

    def __init__(self, conn: sqlite3.Connection, credits: int | None) -> None:
        self.conn = conn
        self.credits = credits
        self.days = _days(conn)
        self.latest = self.days[-1] if self.days else None
        self.template = (
            resources.files("shopledger.templates")
            .joinpath("base.html")
            .read_text(encoding="utf-8")
        )
        last = conn.execute(
            "SELECT * FROM run_log WHERE finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if last is None:
            self.run_pill = '<span class="pill warn"><i class="dot"></i>No run recorded</span>'
        else:
            clean = (last["errors"] or 0) == 0
            state = "clean" if clean else f"{last['errors']} errors"
            klass = "pill" if clean else "pill warn"
            stamp = last["finished_at"][11:16] + " UTC"
            self.run_pill = (
                f'<span class="{klass}"><i class="dot"></i>'
                f"Last run {esc(stamp)} · {esc(state)}</span>"
            )

    def page(
        self,
        *,
        title: str,
        crumb: str,
        active: str,
        content: str,
        script: str = "",
        prefix: str = "",
    ) -> str:
        credits = f"{self.credits:,}" if self.credits is not None else "---"
        out = self.template
        tokens = {
            "__TITLE__": esc(title),
            "__WORDMARK__": wordmark(16),
            "__NAV__": nav(active, prefix),
            "__FOOT__": f"v0.1 · {esc(self.latest or 'no data')}",
            "__CRUMB__": crumb,
            "__RUNPILL__": self.run_pill,
            "__CREDITS__": esc(credits),
            "__CONTENT__": content,
            "__SCRIPT__": script,
        }
        for token, value in tokens.items():
            out = out.replace(token, value)
        return out


# ----------------------------------------------------------------------- pages


def page_index(site: Site) -> str:
    conn, latest = site.conn, site.latest
    series = _series(conn, site.days) if site.days else _empty_series(METRICS)

    if latest:
        units_today = short(series["units"]["values"][-1])
        revenue_today = money(series["revenue"]["values"][-1])
        headline = f"{units_today} units · {revenue_today}"
        day_label = datetime.strptime(latest, "%Y-%m-%d").strftime("%A %d %B %Y")
    else:
        headline = "Waiting on the first delta"
        day_label = "No resolved days yet"

    movers = (
        conn.execute(
            """
            SELECT r.*, p.title, p.pdp_url, p.image_url, p.seller_name, p.category_name
            FROM daily_result r JOIN product p ON p.product_id = r.product_id
            WHERE r.day = ? AND r.units > 0 ORDER BY r.revenue DESC LIMIT 10
            """,
            (latest,),
        ).fetchall()
        if latest
        else []
    )
    videos = (
        conn.execute(
            """
            SELECT a.*, v.url, v.title, v.author_name, v.cover_image_url,
                   p.title AS product_title
            FROM attribution a
            JOIN video v ON v.item_id = a.item_id
            JOIN product p ON p.product_id = a.product_id
            WHERE a.day = ? AND a.view_delta > 0 ORDER BY a.view_delta DESC LIMIT 10
            """,
            (latest,),
        ).fetchall()
        if latest
        else []
    )

    if movers:
        movers_html = "".join(product_row(i, r) for i, r in enumerate(movers, 1))
    elif latest:
        movers_html = empty("No movement recorded on this day.", "Every tracked product held flat.")
    else:
        movers_html = empty(
            "No snapshots resolved yet.",
            "The first delta appears after two runs, because a delta needs two readings.",
        )

    if videos:
        videos_html = "".join(video_row(i, r) for i, r in enumerate(videos, 1))
    elif latest:
        videos_html = empty(
            "No view movement on the panel.",
            "Sales on this day are reported as unattributed rather than assigned.",
        )
    else:
        videos_html = empty(
            "No video panel yet.",
            "Videos arrive with the first detail pull and produce shares one day later.",
        )

    panel = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='tracked'").fetchone()["n"]
    window = f"Last {len(site.days)} days" if site.days else "Last 7 days"

    partial_note = ""
    if latest:
        row = conn.execute(
            "SELECT COUNT(*) AS n, AVG(interval_hours) AS h FROM daily_result "
            "WHERE day = ? AND partial = 1",
            (latest,),
        ).fetchone()
        if row["n"]:
            hours = row["h"] or 0
            partial_note = (
                f'<p class="note">{row["n"]} of these rows were measured over about '
                f"{hours:.1f} hours rather than a full day, because two pulls ran close "
                f"together. They are real readings over a real interval, just not daily "
                f"ones, and they are flagged partial everywhere they appear.</p>"
            )

    content = f"""
      <p class="eyebrow">{esc(day_label)}</p>
      <h1>{headline}</h1>
      {partial_note}
      <div class="ctlbar">
        <span class="ctl">{icon("calendar", 16)}<span class="lbl">Window</span>{esc(window)}</span>
        <span class="ctl"><span class="lbl">Granularity</span>Day</span>
        <span class="ctl">{icon("layers", 16)}<span class="lbl">Panel</span>{panel} tracked</span>
        <a class="ctl" href="products.html">All products{icon("external", 16)}</a>
      </div>
      {_chart_card(series, site.days, METRICS)}
      <div class="grid2">
        <section class="panel"><div class="hd"><h2>Top movers</h2><span class="spacer"></span>
          <span class="meta">by revenue delta</span></div>
          <div class="bd">{movers_html}</div></section>
        <section class="panel videos"><div class="hd"><h2>Top 10 videos</h2>
          <span class="spacer"></span><span class="meta">by view delta</span></div>
          <div class="bd">{videos_html}</div></section>
      </div>
      <section class="health">{_health_units(site)}</section>
    """
    return site.page(
        title="Shop Ledger",
        crumb="Today",
        active="index.html",
        content=content,
        script=_chart_script(series),
    )


def page_products(site: Site) -> str:
    conn = site.conn
    rows = conn.execute(
        """
        SELECT p.product_id, p.title, p.image_url, p.seller_name, p.category_name,
               r.units, r.revenue, r.method, r.confidence, r.unattributed,
               r.interval_hours, r.partial,
               (SELECT sold_count FROM product_snapshot s
                 WHERE s.product_id = p.product_id AND s.sold_count IS NOT NULL
                 ORDER BY captured_at DESC LIMIT 1) AS sold,
               (SELECT rating FROM product_snapshot s
                 WHERE s.product_id = p.product_id AND s.rating IS NOT NULL
                 ORDER BY captured_at DESC LIMIT 1) AS rating
        FROM product p
        LEFT JOIN daily_result r ON r.product_id = p.product_id AND r.day = ?
        WHERE p.tier = 'tracked'
        ORDER BY COALESCE(r.revenue, -1) DESC
        """,
        (site.latest,),
    ).fetchall()

    body = []
    for row in rows:
        search = f"{row['title']} {row['seller_name'] or ''} {row['category_name'] or ''}".lower()
        rating = f"{row['rating']:.1f}" if row["rating"] else "---"
        partial = (
            f' <span class="badge flat">{row["interval_hours"]:.1f}h</span>'
            if row["partial"]
            else ""
        )
        body.append(
            f'<tr data-search="{esc(search)}">'
            f'<td class="prod"><div class="wrap">{thumb(row["image_url"])}'
            f'<div style="min-width:0">'
            f'<a class="t" href="products/{esc(row["product_id"])}.html">{esc(row["title"])}</a>'
            f'<div class="s">{esc(row["seller_name"] or "unknown seller")}</div></div></div></td>'
            f'<td data-sort="{esc(row["category_name"] or "")}">'
            f"{esc(row['category_name'] or '---')}</td>"
            f'<td class="n" data-sort="{row["units"] or 0}">{exact(row["units"])}</td>'
            f'<td class="n" data-sort="{row["revenue"] or 0}">{money(row["revenue"])}</td>'
            f'<td class="n" data-sort="{row["sold"] or 0}">{short(row["sold"])}</td>'
            f'<td class="n" data-sort="{row["rating"] or 0}">{rating}</td>'
            f'<td data-sort="{esc(row["method"] or "")}">'
            f"{esc(row['method'] or '---')}{partial}</td>"
            f'<td class="n" data-sort="{row["confidence"] or 0}">'
            f"{confidence_badge(row['confidence'], row['unattributed'] or 0)}</td>"
            f"</tr>"
        )

    table = sortable_table(
        [
            ("Product", "", True),
            ("Category", "", True),
            ("Units", "n", True),
            ("Revenue", "n", True),
            ("Lifetime sold", "n", True),
            ("Rating", "n", True),
            ("Method", "", True),
            ("Confidence", "n", True),
        ],
        body,
        "No tracked products yet. Run a sweep to build the panel.",
    )

    content = f"""
      <p class="eyebrow">{esc(site.latest or "no resolved day")}</p>
      <h1>Products</h1>
      <p class="note">The tracked panel, ranked by revenue on the latest resolved day. Every
        column sorts. Units and revenue are the day's movement, not lifetime totals.</p>
      <div class="ctlbar">
        <input class="ctl" id="search" type="search"
               placeholder="Filter by title, seller or category">
        <span class="ctl">{icon("layers", 16)}<span class="lbl">Panel</span>{len(rows)}</span>
      </div>
      <div class="panel"><div class="bd flush">{table}</div></div>
    """
    return site.page(
        title="Products · Shop Ledger",
        crumb='<a href="index.html">Today</a> / Products',
        active="products.html",
        content=content,
        script=SORT_SCRIPT,
    )


def page_product(site: Site, product) -> str:
    conn = site.conn
    pid = product["product_id"]
    series = _product_series(conn, pid, site.days)
    latest = conn.execute(
        "SELECT * FROM daily_result WHERE product_id = ? ORDER BY day DESC LIMIT 1", (pid,)
    ).fetchone()
    snap = conn.execute(
        "SELECT * FROM product_snapshot WHERE product_id = ? AND source='detail' "
        "ORDER BY captured_at DESC LIMIT 1",
        (pid,),
    ).fetchone()

    skus = conn.execute(
        """
        SELECT * FROM sku_snapshot WHERE product_id = ?
          AND captured_at = (SELECT MAX(captured_at) FROM sku_snapshot WHERE product_id = ?)
        ORDER BY price DESC
        """,
        (pid, pid),
    ).fetchall()
    sku_rows = [
        f"<tr><td>{esc(s['sku_name'] or s['sku_id'])}</td>"
        f'<td class="n" data-sort="{s["price"] or 0}">{money(s["price"])}</td>'
        f'<td class="n" data-sort="{s["stock"] or 0}">{exact(s["stock"])}</td></tr>'
        for s in skus
    ]
    sku_table = sortable_table(
        [("Variant", "", False), ("Price", "n", True), ("Stock", "n", True)],
        sku_rows,
        "No variant data captured yet.",
    )

    videos = conn.execute(
        """
        SELECT v.*, a.view_delta, a.share, p.title AS product_title
        FROM video v
        JOIN product p ON p.product_id = v.product_id
        LEFT JOIN attribution a ON a.item_id = v.item_id AND a.day = ?
        WHERE v.product_id = ?
        ORDER BY COALESCE(a.view_delta, -1) DESC, v.first_seen DESC LIMIT 25
        """,
        (site.latest, pid),
    ).fetchall()
    if videos:
        video_html = "".join(video_row(i, r, show_product=False) for i, r in enumerate(videos, 1))
    else:
        video_html = empty(
            "No videos captured for this product.", "They arrive with the next detail pull."
        )

    if latest:
        headline = f"{short(latest['units'])} units · {money(latest['revenue'])}"
    else:
        headline = "Awaiting a second snapshot"

    price_range = (
        f"{money(snap['min_price'])} - {money(snap['max_price'])}"
        if snap and snap["min_price"]
        else "---"
    )
    rating = (
        f"{snap['rating']:.1f} ({short(snap['review_count'])} reviews)"
        if snap and snap["rating"]
        else "---"
    )
    deltas = f"{exact(latest['sold_delta'])} vs {exact(latest['stock_delta'])}" if latest else "---"
    if latest and latest["interval_hours"]:
        window = f"{latest['interval_hours']:.1f} hours"
        if latest["partial"]:
            window += ' <span class="badge flat">partial, not a full day</span>'
    else:
        window = "---"
    facts = [
        ("Seller", esc(product["seller_name"] or "unknown")),
        ("Category", esc(product["category_name"] or "unknown")),
        ("Lifetime sold", short(snap["sold_count"]) if snap else "---"),
        ("Stock now", exact(snap["stock_total"]) if snap else "---"),
        ("Price range", price_range),
        ("Rating", rating),
        ("Method", esc(latest["method"]) if latest else "---"),
        (
            "Confidence",
            confidence_badge(latest["confidence"], latest["unattributed"]) if latest else "---",
        ),
        ("Sold vs stock delta", deltas),
        ("Measured over", window),
    ]
    kv = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)

    content = f"""
      <p class="eyebrow">{esc(site.latest or "no resolved day")}</p>
      <h1>{esc(product["title"])}</h1>
      <div class="ctlbar">
        <a class="ctl" href="{esc(product["pdp_url"])}" target="_blank" rel="noopener">
          Open on TikTok Shop{icon("external", 16)}</a>
        <span class="ctl"><span class="lbl">ID</span>{esc(pid)}</span>
        <span class="ctl"><span class="lbl">Today</span>{esc(headline)}</span>
      </div>
      {_chart_card(series, site.days, PRODUCT_METRICS)}
      <div class="grid2">
        <section class="panel"><div class="hd"><h2>Facts</h2></div>
          <dl class="kv">{kv}</dl></section>
        <section class="panel"><div class="hd"><h2>Variants</h2><span class="spacer"></span>
          <span class="meta">stock is exact, per variant</span></div>
          <div class="bd flush">{sku_table}</div></section>
      </div>
      <section class="panel"><div class="hd"><h2>Videos</h2><span class="spacer"></span>
        <span class="meta">ranked by view delta on the latest day</span></div>
        <div class="bd">{video_html}</div></section>
    """
    crumb = '<a href="../index.html">Today</a> / <a href="../products.html">Products</a> / Detail'
    return site.page(
        title=f"{product['title'][:60]} · Shop Ledger",
        crumb=crumb,
        active="products.html",
        content=content,
        script=_chart_script(series) + SORT_SCRIPT,
        prefix="../",
    )


def page_videos(site: Site) -> str:
    conn = site.conn
    rows = conn.execute(
        """
        SELECT v.*, a.view_delta, a.share, a.revenue AS attr_revenue,
               p.title AS product_title, p.product_id AS pid
        FROM video v
        JOIN product p ON p.product_id = v.product_id
        LEFT JOIN attribution a ON a.item_id = v.item_id AND a.day = ?
        WHERE p.tier = 'tracked'
        ORDER BY COALESCE(a.view_delta, -1) DESC, v.last_seen DESC LIMIT 300
        """,
        (site.latest,),
    ).fetchall()

    body = []
    for row in rows:
        title = row["title"] or row["product_title"] or "Untitled video"
        handle = row["author_name"] or "unknown"
        search = f"{title} {handle} {row['product_title']}".lower()
        flag = (
            '<span class="badge flat">commission</span>'
            if row["is_affiliate"]
            else '<span class="badge flat">organic</span>'
        )
        panel = "" if row["in_panel"] else ' <span class="badge flat">off panel</span>'
        views = "+" + short(row["view_delta"]) if row["view_delta"] else "---"
        share = f"{(row['share'] or 0) * 100:.0f}%" if row["share"] else "---"
        body.append(
            f'<tr data-search="{esc(search)}">'
            f'<td class="prod"><div class="wrap">'
            f"{thumb(row['cover_image_url'], tall=True, glyph='play')}"
            f'<div style="min-width:0">'
            f'<a class="t" href="{esc(row["url"])}" target="_blank" rel="noopener">'
            f"{esc(title)}</a>"
            f'<div class="s">@{esc(handle)}</div></div></div></td>'
            f'<td data-sort="{esc(row["product_title"])}">'
            f'<a href="products/{esc(row["pid"])}.html">{esc(row["product_title"][:48])}</a></td>'
            f'<td class="n" data-sort="{row["view_delta"] or 0}">{views}</td>'
            f'<td class="n" data-sort="{row["share"] or 0}">{share}</td>'
            f'<td class="n" data-sort="{row["attr_revenue"] or 0}">'
            f"{money(row['attr_revenue']) if row['attr_revenue'] else '---'}</td>"
            f'<td data-sort="{row["is_affiliate"]}">{flag}{panel}</td>'
            f"</tr>"
        )

    table = sortable_table(
        [
            ("Video", "", True),
            ("Product", "", True),
            ("View delta", "n", True),
            ("Share", "n", True),
            ("Attributed", "n", True),
            ("Type", "", True),
        ],
        body,
        "No videos captured yet. They arrive with the first detail pull.",
    )

    content = f"""
      <p class="eyebrow">{esc(site.latest or "no resolved day")}</p>
      <h1>Videos</h1>
      <p class="note">Every video on the tracked panel. Only commission-flagged videos take part
        in attribution; organic ones are recorded but never assigned sales. Titles link out to
        TikTok.</p>
      <div class="ctlbar">
        <input class="ctl" id="search" type="search"
               placeholder="Filter by title, creator or product">
        <span class="ctl">{icon("play", 16)}<span class="lbl">Videos</span>{len(rows)}</span>
      </div>
      <div class="panel"><div class="bd flush">{table}</div></div>
    """
    return site.page(
        title="Videos · Shop Ledger",
        crumb='<a href="index.html">Today</a> / Videos',
        active="videos.html",
        content=content,
        script=SORT_SCRIPT,
    )


def page_creators(site: Site) -> str:
    conn = site.conn
    rows = conn.execute(
        """
        SELECT v.author_name, v.author_url,
               COUNT(DISTINCT v.item_id)    AS videos,
               COUNT(DISTINCT v.product_id) AS products,
               COALESCE(SUM(a.view_delta), 0) AS views,
               COALESCE(SUM(a.revenue), 0)    AS revenue,
               COALESCE(SUM(a.units), 0)      AS units,
               MAX(v.cover_image_url)         AS cover
        FROM video v
        LEFT JOIN attribution a ON a.item_id = v.item_id AND a.day = ?
        WHERE v.author_name IS NOT NULL AND v.is_affiliate = 1
        GROUP BY v.author_name
        ORDER BY revenue DESC, views DESC
        LIMIT 200
        """,
        (site.latest,),
    ).fetchall()

    body = []
    for row in rows:
        handle = row["author_name"]
        plural = "s" if row["products"] != 1 else ""
        body.append(
            f'<tr data-search="{esc(handle.lower())}">'
            f'<td class="prod"><div class="wrap">{thumb(row["cover"], glyph="users")}'
            f'<div style="min-width:0"><a class="t" href="{esc(row["author_url"] or "#")}" '
            f'target="_blank" rel="noopener">@{esc(handle)}</a>'
            f'<div class="s">{row["products"]} product{plural}</div></div></div></td>'
            f'<td class="n" data-sort="{row["videos"]}">{exact(row["videos"])}</td>'
            f'<td class="n" data-sort="{row["views"]}">'
            f"{'+' + short(row['views']) if row['views'] else '---'}</td>"
            f'<td class="n" data-sort="{row["units"]}">'
            f"{short(row['units']) if row['units'] else '---'}</td>"
            f'<td class="n" data-sort="{row["revenue"]}">'
            f"{money(row['revenue']) if row['revenue'] else '---'}</td>"
            f"</tr>"
        )

    table = sortable_table(
        [
            ("Creator", "", True),
            ("Videos", "n", True),
            ("View delta", "n", True),
            ("Units", "n", True),
            ("Attributed revenue", "n", True),
        ],
        body,
        "No commission-flagged creators yet.",
    )

    content = f"""
      <p class="eyebrow">{esc(site.latest or "no resolved day")}</p>
      <h1>Creators</h1>
      <p class="note">Affiliates ranked by the revenue attributed to their videos on the latest
        resolved day. A creator appearing across several products is the stronger signal, since
        one viral video is luck and three is a method.</p>
      <div class="ctlbar">
        <input class="ctl" id="search" type="search" placeholder="Filter by handle">
        <span class="ctl">{icon("users", 16)}<span class="lbl">Creators</span>{len(rows)}</span>
      </div>
      <div class="panel"><div class="bd flush">{table}</div></div>
    """
    return site.page(
        title="Creators · Shop Ledger",
        crumb='<a href="index.html">Today</a> / Creators',
        active="creators.html",
        content=content,
        script=SORT_SCRIPT,
    )


def _health_units(site: Site) -> str:
    conn, day = site.conn, site.latest
    stats: dict[str, object] = {
        "Restock flags": 0,
        "Low confidence": 0,
        "Provisional": 0,
        "Partial intervals": 0,
        "Unattributed units": 0,
    }
    if day:
        row = conn.execute(
            """
            SELECT SUM(restock) AS restocks,
                   SUM(CASE WHEN confidence < 0.3 THEN 1 ELSE 0 END) AS low,
                   SUM(provisional) AS prov,
                   SUM(partial) AS part,
                   SUM(unattributed) AS unattr
            FROM daily_result WHERE day = ?
            """,
            (day,),
        ).fetchone()
        stats = {
            "Restock flags": row["restocks"] or 0,
            "Low confidence": row["low"] or 0,
            "Provisional": row["prov"] or 0,
            "Partial intervals": row["part"] or 0,
            "Unattributed units": row["unattr"] or 0,
        }

    stats["Panel"] = conn.execute(
        "SELECT COUNT(*) AS n FROM product WHERE tier='tracked'"
    ).fetchone()["n"]
    stats["Watchlist"] = conn.execute(
        "SELECT COUNT(*) AS n FROM product WHERE tier='watch'"
    ).fetchone()["n"]
    stats["Credits left"] = f"{site.credits:,}" if site.credits is not None else "---"

    return "".join(
        f'<div class="u"><span class="k">{esc(k)}</span>'
        f'<span class="v">{esc(v if isinstance(v, str) else f"{v:,}")}</span></div>'
        for k, v in stats.items()
    )


def page_health(site: Site) -> str:
    conn = site.conn
    runs = conn.execute("SELECT * FROM run_log ORDER BY started_at DESC LIMIT 30").fetchall()
    run_rows = [
        f"<tr><td>{esc(r['started_at'][:16].replace('T', ' '))}</td>"
        f"<td>{esc(r['stage'])}</td>"
        f'<td class="n" data-sort="{r["calls"] or 0}">{exact(r["calls"])}</td>'
        f'<td class="n" data-sort="{r["errors"] or 0}">{exact(r["errors"])}</td>'
        f'<td class="n" data-sort="{r["credits_after"] or 0}">{exact(r["credits_after"])}</td>'
        f"<td>{'finished' if r['finished_at'] else 'did not finish'}</td></tr>"
        for r in runs
    ]
    run_table = sortable_table(
        [
            ("Started", "", True),
            ("Stage", "", True),
            ("Calls", "n", True),
            ("Errors", "n", True),
            ("Credits after", "n", True),
            ("Outcome", "", True),
        ],
        run_rows,
        "No runs recorded yet.",
        table_id="runs",
    )

    flagged = (
        conn.execute(
            """
            SELECT r.*, p.title FROM daily_result r JOIN product p ON p.product_id = r.product_id
            WHERE r.day = ?
              AND (r.restock = 1 OR r.confidence < 0.3 OR r.provisional = 1 OR r.partial = 1)
            ORDER BY r.revenue DESC LIMIT 50
            """,
            (site.latest,),
        ).fetchall()
        if site.latest
        else []
    )
    flag_rows = []
    for row in flagged:
        reasons = []
        if row["restock"]:
            reasons.append("restock")
        if row["confidence"] < 0.3:
            reasons.append("low confidence")
        if row["provisional"]:
            reasons.append("provisional")
        if row["partial"]:
            reasons.append(f"partial {row['interval_hours']:.1f}h")
        flag_rows.append(
            f'<tr><td class="prod"><a class="t" '
            f'href="products/{esc(row["product_id"])}.html">{esc(row["title"])}</a></td>'
            f'<td data-sort="{esc(", ".join(reasons))}">{esc(", ".join(reasons))}</td>'
            f'<td class="n" data-sort="{row["units"]}">{exact(row["units"])}</td>'
            f'<td class="n" data-sort="{row["sold_delta"] or 0}">{exact(row["sold_delta"])}</td>'
            f'<td class="n" data-sort="{row["stock_delta"] or 0}">{exact(row["stock_delta"])}</td>'
            f"</tr>"
        )
    flag_table = sortable_table(
        [
            ("Product", "", True),
            ("Flags", "", True),
            ("Units used", "n", True),
            ("Sold delta", "n", True),
            ("Stock delta", "n", True),
        ],
        flag_rows,
        "Nothing flagged on the latest day.",
        table_id="flags",
    )

    content = f"""
      <p class="eyebrow">{esc(site.latest or "no resolved day")}</p>
      <h1>Data health</h1>
      <p class="note">Where the numbers are soft. A paid tool has no interest in showing you this,
        which is exactly why it is here. Rows carrying a sold delta and a stock delta that
        disagree are kept as they were measured, so the gap stays auditable.</p>
      <section class="health">{_health_units(site)}</section>
      <section class="panel" style="margin-top:16px"><div class="hd"><h2>Flagged rows</h2>
        <span class="spacer"></span><span class="meta">latest resolved day</span></div>
        <div class="bd flush">{flag_table}</div></section>
      <section class="panel"><div class="hd"><h2>Run log</h2><span class="spacer"></span>
        <span class="meta">last 30 runs</span></div>
        <div class="bd flush">{run_table}</div></section>
    """
    return site.page(
        title="Data health · Shop Ledger",
        crumb='<a href="index.html">Today</a> / Data health',
        active="health.html",
        content=content,
        script=SORT_SCRIPT,
    )


# ------------------------------------------------------------------------ site


def render(conn: sqlite3.Connection, out_dir: Path, credits: int | None = None) -> Path:
    """Write the whole site. Returns the path of the entry page."""
    if out_dir.suffix == ".html":  # tolerate a file path being passed
        out_dir = out_dir.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    products_dir = out_dir / "products"
    if products_dir.exists():
        shutil.rmtree(products_dir)
    products_dir.mkdir(parents=True, exist_ok=True)

    site = Site(conn, credits)
    for name, builder in (
        ("index.html", page_index),
        ("products.html", page_products),
        ("videos.html", page_videos),
        ("creators.html", page_creators),
        ("health.html", page_health),
    ):
        (out_dir / name).write_text(builder(site), encoding="utf-8")

    for product in conn.execute("SELECT * FROM product WHERE tier='tracked'").fetchall():
        page = page_product(site, product)
        (products_dir / f"{product['product_id']}.html").write_text(page, encoding="utf-8")

    return out_dir / "index.html"
