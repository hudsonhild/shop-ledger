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
    LIST_CSS,
    TABLE_SCRIPT,
    avatar,
    badge,
    banner,
    button,
    card,
    cell,
    confidence_badge,
    empty,
    esc,
    exact,
    footer_help,
    index_filters,
    index_table,
    kv,
    metric_card,
    missing,
    money,
    nav,
    product_row,
    resource,
    row,
    run_status,
    short,
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
        f'<section class="Polaris-Card"><div class="strip" role="group" '
        f'aria-label="Choose a metric to plot">{_strip(series, metrics)}</div>'
        f'<div class="plot"><svg id="plot" viewBox="0 0 760 170" preserveAspectRatio="none" '
        f'role="img" aria-label="Daily series for the selected metric"></svg>'
        f'<div class="axis"><span>{esc(first)}</span><span>{esc(last)}</span></div></div></section>'
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
        self.last_run = conn.execute(
            "SELECT * FROM run_log WHERE finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        self.run_pill = run_status(self.last_run)
        self.tracked_ids = [
            r["product_id"]
            for r in conn.execute(
                "SELECT product_id FROM product WHERE tier='tracked' ORDER BY title"
            ).fetchall()
        ]

    def page(
        self,
        *,
        title: str,
        active: str,
        content: str,
        script: str = "",
        prefix: str = "",
        search_placeholder: str = "Search products",
    ) -> str:
        credits = f"{self.credits:,}" if self.credits is not None else "---"
        out = self.template
        tokens = {
            "__TITLE__": esc(title),
            "__WORDMARK__": wordmark(20),
            "__NAV__": nav(active, prefix),
            "__FOOT__": f"v0.2 · {esc(self.latest or 'no data')}",
            "__RUNPILL__": self.run_pill,
            "__CREDITS__": esc(credits) + " credits",
            "__CONTENT__": content,
            "__SCRIPT__": LIST_CSS + TABLE_SCRIPT + script,
            "__PREFIX__": prefix,
            "__SEARCH_PLACEHOLDER__": esc(search_placeholder),
            "__ICON_MENU__": icon("menu", 20),
            "__ICON_SEARCH__": icon("search", 20),
            "__ICON_MONEY__": icon("money", 16),
        }
        for token, value in tokens.items():
            out = out.replace(token, value)
        return out


def _header(
    title: str,
    *,
    subtitle: str = "",
    back: str | None = None,
    actions: str = "",
    badge_html: str = "",
    pagination: str = "",
    long: bool = False,
) -> str:
    """Polaris Page header: back button, 18/24 title, badge, then the actions."""
    back_html = button("Back", href=back, variant="secondary", icon_name="arrow-left", icon_only=True) if back else ""
    cls = "Polaris-Page-Header__Title long" if long else "Polaris-Page-Header__Title"
    sub = f'<p class="Polaris-Page-Header__Subtitle">{subtitle}</p>' if subtitle else ""
    return (
        '<div class="Polaris-Page-Header"><div class="Polaris-Page-Header__Row">'
        f'<div class="Polaris-Page-Header__TitleWrapper">{back_html}<h1 class="{cls}">{esc(title)}</h1>{badge_html}</div>'
        f'<div class="Polaris-Page-Header__RightAlign">{actions}{pagination}</div></div>{sub}</div>'
    )


def _page(content: str, full_width: bool = False) -> str:
    cls = "Polaris-Page Polaris-Page--fullWidth" if full_width else "Polaris-Page"
    return f'<div class="{cls}">{content}</div>'


def _delta(values: list[float] | None) -> float | None:
    if not values or len(values) < 2 or not values[-2]:
        return None
    return (values[-1] - values[-2]) / abs(values[-2])


def _day_label(day: str | None) -> str:
    if not day:
        return "No resolved days yet"
    return datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B %Y")


# ----------------------------------------------------------------------- pages


def page_index(site: Site) -> str:
    conn, latest = site.conn, site.latest
    series = _series(conn, site.days) if site.days else _empty_series(METRICS)
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
        movers_html = empty("No movement recorded on this day", "Every tracked product held flat.")
    else:
        movers_html = empty(
            "No snapshots resolved yet",
            "The first delta appears after two runs, because a delta needs two readings.",
        )
    if videos:
        videos_html = "".join(video_row(i, r) for i, r in enumerate(videos, 1))
    elif latest:
        videos_html = empty(
            "No view movement on the panel",
            "Sales on this day are reported as unattributed rather than assigned.",
        )
    else:
        videos_html = empty(
            "No video panel yet",
            "Videos arrive with the first detail pull and produce shares one day later.",
        )
    panel = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='tracked'").fetchone()["n"]

    banner_html = ""
    if latest:
        row = conn.execute(
            "SELECT COUNT(*) AS n, AVG(interval_hours) AS h FROM daily_result "
            "WHERE day = ? AND partial = 1",
            (latest,),
        ).fetchone()
        if row["n"]:
            banner_html = banner(
                f"{row['n']} rows were measured over about {(row['h'] or 0):.1f} hours, not a full day",
                "Two pulls ran close together. They are real readings over a real interval, "
                "just not daily ones, and they are flagged partial everywhere they appear.",
                tone="info",
            )

    metric_html = "".join(
        metric_card(
            label,
            (
                money(series[key]["values"][-1])
                if kind == "money"
                else f"{series[key]['values'][-1]:.0f}"
                if kind == "percent"
                else short(series[key]["values"][-1])
            )
            if series.get(key, {}).get("values")
            else missing(),
            unit="%" if kind == "percent" else "",
            delta=_delta(series.get(key, {}).get("values")),
            series=series.get(key, {}).get("values"),
            tooltip=tip,
        )
        for key, label, kind, tip in (
            ("units", "Units sold", "count", "Units moved on the latest resolved day"),
            ("revenue", "Revenue", "money", "Units times the captured price"),
            ("attributed", "Attributed", "percent", "Share of units assigned to a video"),
            ("entrants", "New entrants", "count", "Products first seen today"),
        )
    )
    window = f"Last {len(site.days)} days" if site.days else "Last 7 days"
    actions = (
        button(window, icon_name="calendar", attrs=' data-tooltip="The resolved days in this report"')
        + button(f"{panel} tracked", icon_name="layers", href="products.html")
    )
    content = _header(
        _day_label(latest),
        subtitle=f"Resolved {esc(latest)}" if latest else "Waiting on the first delta",
        actions=actions,
    )
    content += '<div class="Polaris-BlockStack">'
    if banner_html:
        content += banner_html
    content += _chart_card(series, site.days, METRICS)
    content += (
        '<div class="Polaris-Layout">'
        f'<div class="Polaris-Layout__Section">{card(movers_html, title="Top movers", meta="by revenue delta")}</div>'
        f'<div class="Polaris-Layout__Section">{card(videos_html, title="Top 10 videos", meta="by view delta")}</div>'
        "</div>"
    )
    content += card(_health_units(site), title="Data health", meta="latest resolved day",
                    actions=button("Open", href="health.html", variant="plain"))
    content += "</div>"
    content += footer_help('Learn more about <a class="Polaris-Link" href="health.html">how the numbers are measured</a>')
    return site.page(
        title="Today · Shop Ledger",
        active="index.html",
        content=_page(content),
        script=_chart_script(series),
    )


def page_products(site: Site) -> str:
    conn = site.conn
    rows = conn.execute(
        """
        SELECT p.product_id, p.title, p.image_url, p.seller_name, p.category_name,
               r.units, r.revenue, r.method, r.confidence, r.unattributed,
               r.interval_hours, r.partial, r.restock, r.provisional,
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
    counts = {"moving": 0, "flagged": 0, "flat": 0}
    for r in rows:
        tabs = ["all"]
        if r["units"]:
            tabs.append("moving"); counts["moving"] += 1
        else:
            tabs.append("flat"); counts["flat"] += 1
        if r["restock"] or r["provisional"] or r["partial"] or (r["confidence"] is not None and r["confidence"] < 0.3):
            tabs.append("flagged"); counts["flagged"] += 1
        search = f"{r['title']} {r['seller_name'] or ''} {r['category_name'] or ''}"
        method = badge(r["method"], tooltip="How the day's units were resolved") if r["method"] else missing()
        if r["partial"]:
            method += " " + badge("Partial", "attention", tooltip=f"Measured over {r['interval_hours']:.1f} hours, not a full day")
        if r["restock"]:
            method += " " + badge("restock", "info")
        rating = f"{r['rating']:.1f}" if r["rating"] else missing()
        href = f"products/{r['product_id']}.html"
        body.append(
            row(
                [
                    cell(resource(r["title"], r["seller_name"] or "unknown seller", thumb(r["image_url"]), href=href), primary=True, sort=r["title"]),
                    cell(f'<span class="Polaris-IndexTable__TableCell--truncate" style="display:block" data-tooltip="{esc(r["category_name"] or "")}">{esc(r["category_name"] or "---")}</span>', sort=r["category_name"] or ""),
                    cell(exact(r["units"]) if r["units"] is not None else missing(), align="end", sort=r["units"] or 0),
                    cell(money(r["revenue"]) if r["revenue"] is not None else missing(), align="end", sort=r["revenue"] or 0),
                    cell(short(r["sold"]) if r["sold"] is not None else missing(), align="end", sort=r["sold"] or 0),
                    cell(rating, align="end", sort=r["rating"] or 0),
                    cell(method, sort=r["method"] or ""),
                    cell(confidence_badge(r["confidence"], r["unattributed"] or 0), align="end", sort=r["confidence"] or 0),
                ],
                search=search,
                tab=" ".join(tabs),
                href=href,
            )
        )

    columns = [
        ("Product", "", True),
        ("Category", "", True),
        ("Units", "end", True),
        ("Revenue", "end", True),
        ("Lifetime sold", "end", True),
        ("Rating", "end", True),
        ("Method", "", True),
        ("Confidence", "end", True),
    ]
    table = index_table(columns, body, "No tracked products yet", table_id="products",
                        empty_hint="Run a sweep to build the panel.")
    filters = index_filters(
        [("All", "all", len(rows)), ("Moving", "moving", counts["moving"]), ("Flat", "flat", counts["flat"]), ("Flagged", "flagged", counts["flagged"])],
        search_id="products-search",
        search_placeholder="Search by title, seller or category",
        sort_options=[(label, str(i)) for i, (label, _, s) in enumerate(columns) if s],
        table_id="products",
    )
    content = _header(
        "Products",
        subtitle=f"The tracked panel on {esc(site.latest)}. Units and revenue are the day's movement, not lifetime totals." if site.latest else "No resolved day yet.",
        actions=button("Data health", href="health.html") + button("Today", href="index.html", variant="primary", icon_name="home"),
    )
    content += card(filters + table, flush=True)
    content += footer_help('Every column sorts. Tabs filter the panel by whether it moved or carries a flag.')
    return site.page(
        title="Products · Shop Ledger",
        active="products.html",
        content=_page(content, full_width=True),
        search_placeholder="Search products",
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
        row([
            cell(esc(s["sku_name"] or s["sku_id"]), sort=s["sku_name"] or ""),
            cell(money(s["price"]), align="end", sort=s["price"] or 0),
            cell(exact(s["stock"]), align="end", sort=s["stock"] or 0),
        ])
        for s in skus
    ]
    sku_table = index_table(
        [("Variant", "", False), ("Price", "end", True), ("Stock", "end", True)],
        sku_rows, "No variant data captured yet", table_id="variants", paginate=False,
        empty_hint="Variants arrive with the next detail pull.",
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
        video_html = empty("No videos captured for this product", "They arrive with the next detail pull.", glyph="play")

    price_range = f"{money(snap['min_price'])} - {money(snap['max_price'])}" if snap and snap["min_price"] else missing()
    rating = f"{snap['rating']:.1f} ({short(snap['review_count'])} reviews)" if snap and snap["rating"] else missing()
    if latest and latest["interval_hours"]:
        window = f"{latest['interval_hours']:.1f} hours"
        if latest["partial"]:
            window += " " + badge("partial, not a full day", "attention")
    else:
        window = missing()

    facts = kv([
        ("Seller", esc(product["seller_name"] or "unknown")),
        ("Category", esc(product["category_name"] or "unknown")),
        ("Product ID", f'<button class="Polaris-Button Polaris-Button--variantPlain" type="button" data-copy="{esc(pid)}" data-tooltip="Copy to clipboard">{esc(pid)}</button>'),
        ("Price range", price_range),
        ("Rating", rating),
    ])
    measurement = kv([
        ("Method", badge(latest["method"]) if latest and latest["method"] else missing()),
        ("Confidence", confidence_badge(latest["confidence"], latest["unattributed"]) if latest else missing()),
        ("Sold vs stock delta", f"{exact(latest['sold_delta'])} vs {exact(latest['stock_delta'])}" if latest else missing()),
        ("Measured over", window),
        ("Lifetime sold", short(snap["sold_count"]) if snap else missing()),
        ("Stock now", exact(snap["stock_total"]) if snap else missing()),
    ])
    status_tone, status_label = ("success", "Moving") if latest and latest["units"] else ("", "Flat")
    if latest and (latest["provisional"] or latest["partial"]):
        status_tone, status_label = "attention", "Provisional"

    ids = site.tracked_ids
    pos = ids.index(pid) if pid in ids else -1
    prev_id = ids[pos - 1] if pos > 0 else None
    next_id = ids[pos + 1] if 0 <= pos < len(ids) - 1 else None
    pagination = (
        '<div class="Polaris-Page-Header__Pagination Polaris-ButtonGroup Polaris-ButtonGroup--segmented">'
        + button("Previous product", href=f"{prev_id}.html" if prev_id else None, icon_name="chevron-left", icon_only=True, disabled=not prev_id)
        + button("Next product", href=f"{next_id}.html" if next_id else None, icon_name="chevron-right", icon_only=True, disabled=not next_id)
        + "</div>"
    )
    header = _header(
        product["title"],
        back="../products.html",
        badge_html=badge(status_label, status_tone),
        actions=button("Open on TikTok Shop", href=product["pdp_url"], icon_name="external", external=True),
        pagination=pagination,
        long=True,
    )
    metrics = "".join(
        metric_card(label, (money(vals[-1]) if kind == "money" else short(vals[-1])) if vals else missing(),
                    delta=_delta(vals), series=vals)
        for key, label, kind in PRODUCT_METRICS
        for vals in [series.get(key, {}).get("values")]
    )
    primary = (
        _chart_card(series, site.days, PRODUCT_METRICS)
        + card(sku_table, title="Variants", meta="stock is exact, per variant", flush=True)
        + card(video_html, title="Videos", meta="ranked by view delta on the latest day")
    )
    secondary = card(facts, title="Product") + card(measurement, title="Measurement")
    content = header + (
        '<div class="Polaris-Layout">'
        f'<div class="Polaris-Layout__Section"><div class="Polaris-BlockStack">{primary}</div></div>'
        f'<div class="Polaris-Layout__Section Polaris-Layout__Section--secondary"><div class="Polaris-BlockStack">{secondary}</div></div>'
        "</div>"
    )
    return site.page(
        title=f"{product['title'][:60]} · Shop Ledger",
        active="products.html",
        content=_page(content),
        script=_chart_script(series),
        prefix="../",
        search_placeholder="Search products",
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
    counts = {"commission": 0, "organic": 0}
    for r in rows:
        title = r["title"] or r["product_title"] or "Untitled video"
        handle = r["author_name"] or "unknown"
        kind = "commission" if r["is_affiliate"] else "organic"
        counts[kind] += 1
        flag = badge("Commission", "info") if r["is_affiliate"] else badge("Organic")
        if not r["in_panel"]:
            flag += " " + badge("Off panel", "attention")
        views = "+" + short(r["view_delta"]) if r["view_delta"] else missing()
        share = f"{(r['share'] or 0) * 100:.0f}%" if r["share"] else missing()
        body.append(
            row(
                [
                    cell(resource(title, f"@{handle}", thumb(r["cover_image_url"], tall=True, glyph="play"), href=r["url"], external=True), primary=True, sort=title),
                    cell(f'<a class="Polaris-Link" href="products/{esc(r["pid"])}.html">{esc(r["product_title"][:48])}</a>', sort=r["product_title"]),
                    cell(views, align="end", sort=r["view_delta"] or 0),
                    cell(share, align="end", sort=r["share"] or 0),
                    cell(money(r["attr_revenue"]) if r["attr_revenue"] else missing(), align="end", sort=r["attr_revenue"] or 0),
                    cell(flag, sort=r["is_affiliate"]),
                ],
                search=f"{title} {handle} {r['product_title']}",
                tab=f"all {kind}",
            )
        )
    columns = [
        ("Video", "", True),
        ("Product", "", True),
        ("View delta", "end", True),
        ("Share", "end", True),
        ("Attributed", "end", True),
        ("Type", "", True),
    ]
    table = index_table(columns, body, "No videos captured yet", table_id="videos",
                        empty_hint="They arrive with the first detail pull.")
    filters = index_filters(
        [("All", "all", len(rows)), ("Commission", "commission", counts["commission"]), ("Organic", "organic", counts["organic"])],
        search_id="videos-search", search_placeholder="Search by title, creator or product",
        sort_options=[(label, str(i)) for i, (label, _, s) in enumerate(columns) if s], table_id="videos",
    )
    content = _header(
        "Videos",
        subtitle="Every video on the tracked panel. Only commission-flagged videos take part in attribution; organic ones are recorded but never assigned sales.",
        actions=button("Creators", href="creators.html"),
    )
    content += card(filters + table, flush=True)
    content += footer_help("Titles open on TikTok in a new tab.")
    return site.page(
        title="Videos · Shop Ledger", active="videos.html",
        content=_page(content, full_width=True), search_placeholder="Search videos",
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
    multi = 0
    for r in rows:
        handle = r["author_name"]
        plural = "s" if r["products"] != 1 else ""
        tabs = ["all"]
        if r["products"] > 1:
            tabs.append("multi"); multi += 1
        body.append(
            row(
                [
                    cell(resource(f"@{handle}", f"{r['products']} product{plural}", avatar(handle), href=r["author_url"] or None, external=True), primary=True, sort=handle),
                    cell(exact(r["videos"]), align="end", sort=r["videos"]),
                    cell("+" + short(r["views"]) if r["views"] else missing(), align="end", sort=r["views"]),
                    cell(short(r["units"]) if r["units"] else missing(), align="end", sort=r["units"]),
                    cell(money(r["revenue"]) if r["revenue"] else missing(), align="end", sort=r["revenue"]),
                ],
                search=handle, tab=" ".join(tabs),
            )
        )
    columns = [
        ("Creator", "", True),
        ("Videos", "end", True),
        ("View delta", "end", True),
        ("Units", "end", True),
        ("Attributed revenue", "end", True),
    ]
    table = index_table(columns, body, "No commission-flagged creators yet", table_id="creators",
                        empty_hint="Creators appear once an affiliate video is captured.")
    filters = index_filters(
        [("All", "all", len(rows)), ("Across products", "multi", multi)],
        search_id="creators-search", search_placeholder="Search by handle",
        sort_options=[(label, str(i)) for i, (label, _, s) in enumerate(columns) if s], table_id="creators",
    )
    content = _header(
        "Creators",
        subtitle="Affiliates ranked by the revenue attributed to their videos on the latest resolved day. A creator across several products is the stronger signal: one viral video is luck and three is a method.",
        actions=button("Videos", href="videos.html"),
    )
    content += card(filters + table, flush=True)
    content += footer_help("Handles open the creator on TikTok.")
    return site.page(
        title="Creators · Shop Ledger", active="creators.html",
        content=_page(content, full_width=True), search_placeholder="Search creators",
    )


def _health_units(site: Site) -> str:
    conn, day = site.conn, site.latest
    stats: dict[str, object] = {
        "Restock flags": 0, "Low confidence": 0, "Provisional": 0,
        "Partial intervals": 0, "Unattributed units": 0,
    }
    if day:
        r = conn.execute(
            """
            SELECT SUM(restock) AS restocks,
                   SUM(CASE WHEN confidence < 0.3 THEN 1 ELSE 0 END) AS low,
                   SUM(provisional) AS prov, SUM(partial) AS part, SUM(unattributed) AS unattr
            FROM daily_result WHERE day = ?
            """,
            (day,),
        ).fetchone()
        stats = {
            "Restock flags": r["restocks"] or 0, "Low confidence": r["low"] or 0,
            "Provisional": r["prov"] or 0, "Partial intervals": r["part"] or 0,
            "Unattributed units": r["unattr"] or 0,
        }
    stats["Panel"] = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='tracked'").fetchone()["n"]
    stats["Watchlist"] = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='watch'").fetchone()["n"]
    stats["Credits left"] = f"{site.credits:,}" if site.credits is not None else None
    return (
        '<div class="Polaris-InlineGrid" style="grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));gap:var(--p-space-300) var(--p-space-500)">'
        + "".join(
            f'<div><div class="t-body-sm t-subdued">{esc(k)}</div>'
            f'<div class="t-heading-md t-num">{esc(v if isinstance(v, str) else f"{v:,}") if v is not None else missing()}</div></div>'
            for k, v in stats.items()
        )
        + "</div>"
    )


def page_health(site: Site) -> str:
    conn = site.conn
    runs = conn.execute("SELECT * FROM run_log ORDER BY started_at DESC LIMIT 30").fetchall()
    run_rows = [
        row([
            cell(esc(r["started_at"][:16].replace("T", " ")), sort=r["started_at"]),
            cell(badge(r["stage"]), sort=r["stage"]),
            cell(exact(r["calls"]), align="end", sort=r["calls"] or 0),
            cell(exact(r["errors"]) if not r["errors"] else badge(exact(r["errors"]), "critical"), align="end", sort=r["errors"] or 0),
            cell(exact(r["credits_after"]), align="end", sort=r["credits_after"] or 0),
            cell(badge("Finished", "success", pip="complete") if r["finished_at"] else badge("Did not finish", "critical", pip="incomplete"), sort=1 if r["finished_at"] else 0),
        ])
        for r in runs
    ]
    run_table = index_table(
        [("Started", "", True), ("Stage", "", True), ("Calls", "end", True), ("Errors", "end", True),
         ("Credits after", "end", True), ("Outcome", "", True)],
        run_rows, "No runs recorded yet", table_id="runs", paginate=False,
        empty_hint="The first run writes a row here.",
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
    for r in flagged:
        reasons = []
        if r["restock"]:
            reasons.append(badge("Restock", "info"))
        if r["confidence"] < 0.3:
            reasons.append(badge("Low confidence", "critical"))
        if r["provisional"]:
            reasons.append(badge("Provisional", "attention"))
        if r["partial"]:
            reasons.append(badge(f"Partial {r['interval_hours']:.1f}h", "attention"))
        flag_rows.append(
            row([
                cell(f'<a class="t" href="products/{esc(r["product_id"])}.html" data-tooltip="{esc(r["title"])}">{esc(r["title"])}</a>', primary=True, sort=r["title"]),
                cell(f'<span style="display:inline-flex;flex-wrap:wrap;gap:var(--p-space-100);max-width:18rem;white-space:normal">{"".join(reasons)}</span>', sort=len(reasons)),
                cell(exact(r["units"]), align="end", sort=r["units"]),
                cell(exact(r["sold_delta"]), align="end", sort=r["sold_delta"] or 0),
                cell(exact(r["stock_delta"]), align="end", sort=r["stock_delta"] or 0),
            ], search=r["title"], href=f"products/{r['product_id']}.html")
        )
    flag_table = index_table(
        [("Product", "", True), ("Flags", "", True), ("Units used", "end", True),
         ("Sold delta", "end", True), ("Stock delta", "end", True)],
        flag_rows, "Nothing flagged on the latest day", table_id="flags",
        empty_hint="Every row resolved cleanly.",
    )
    content = _header(
        "Data health",
        subtitle="Where the numbers are soft. A paid tool has no interest in showing you this, which is exactly why it is here.",
        actions=button("Products", href="products.html"),
    )
    content += '<div class="Polaris-BlockStack">'
    content += banner(
        "Rows whose sold delta and stock delta disagree are kept as measured",
        "The gap stays auditable rather than being smoothed away. Confidence below 0.3 means the two readings could not be reconciled.",
        tone="info",
    )
    content += card(_health_units(site), title="Latest resolved day")
    content += card(flag_table, title="Flagged rows", meta="latest resolved day", flush=True)
    content += card(run_table, title="Run log", meta="last 30 runs", flush=True)
    content += "</div>"
    return site.page(
        title="Data health · Shop Ledger", active="health.html", content=_page(content),
        search_placeholder="Search flagged rows",
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
