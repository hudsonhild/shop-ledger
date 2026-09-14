"""Render the dashboard to a standalone HTML file.

No template engine and no build step: the template is plain HTML with __TOKEN__
placeholders, so anyone can restyle it by editing one file.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime
from importlib import resources
from pathlib import Path

from .icons import icon, wordmark

WINDOW_DAYS = 7


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def short(n: float | None) -> str:
    if n is None:
        return "---"
    n = float(n)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            return f"{n / limit:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{n:,.0f}"


def money(n: float | None) -> str:
    if n is None:
        return "---"
    return "$" + short(n)


def _days(conn: sqlite3.Connection, limit: int = WINDOW_DAYS) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT day FROM daily_result ORDER BY day DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r["day"] for r in reversed(rows)]


def _series(conn: sqlite3.Connection, days: list[str]) -> dict:
    out = {
        "units": {"values": [], "money": False},
        "revenue": {"values": [], "money": True},
        "tracked": {"values": [], "money": False},
        "attributed": {"values": [], "money": False},
        "entrants": {"values": [], "money": False},
    }
    for day in days:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(units),0)  AS units,
                   COALESCE(SUM(revenue),0) AS revenue,
                   COUNT(*)                 AS tracked,
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


def _strip(series: dict) -> str:
    spec = [
        ("units", "Units sold", lambda v: short(v)),
        ("revenue", "Revenue", lambda v: money(v)),
        ("tracked", "Tracked products", lambda v: short(v)),
        ("attributed", "Attributed", lambda v: f"{v:.0f}<small>%</small>"),
        ("entrants", "New entrants", lambda v: short(v)),
    ]
    cells = []
    for index, (key, label, fmt) in enumerate(spec):
        values = series[key]["values"]
        value = fmt(values[-1]) if values else "---"
        pressed = "true" if index == 0 else "false"
        cells.append(
            f'<button class="cell" type="button" data-key="{key}" aria-pressed="{pressed}">'
            f'<div class="lab">{esc(label)}</div><div class="val">{value}</div></button>'
        )
    return "".join(cells)


def _empty(title: str, hint: str) -> str:
    return (
        f'<div class="empty">{icon("chart-empty", 32)}'
        f"<p>{esc(title)}</p><p>{esc(hint)}</p></div>"
    )


def _movers(conn: sqlite3.Connection, day: str | None) -> str:
    if not day:
        return _empty(
            "No snapshots resolved yet.",
            "The first delta appears after two runs, because a delta needs two readings.",
        )
    rows = conn.execute(
        """
        SELECT r.*, p.title, p.pdp_url, p.image_url, p.seller_name, p.category_name
        FROM daily_result r JOIN product p ON p.product_id = r.product_id
        WHERE r.day = ? AND r.units > 0
        ORDER BY r.revenue DESC LIMIT 10
        """,
        (day,),
    ).fetchall()
    if not rows:
        return _empty("No movement recorded on this day.", "Every tracked product held flat.")

    items = []
    for index, row in enumerate(rows, 1):
        if row["confidence"] >= 0.6:
            badge = f'<span class="badge up">{row["confidence"]:.2f}</span>'
        elif row["confidence"] >= 0.3:
            badge = f'<span class="badge flat">{row["confidence"]:.2f}</span>'
        else:
            badge = '<span class="badge down">unattributed</span>'
        flags = ' <span class="badge flat">restock</span>' if row["restock"] else ""

        thumb = (
            f'<img class="thumb" src="{esc(row["image_url"])}" alt="" loading="lazy">'
            if row["image_url"]
            else f'<span class="thumb ph">{icon("image", 15)}</span>'
        )
        sub = " · ".join(
            part for part in (row["seller_name"], row["category_name"], row["method"]) if part
        )
        items.append(
            f'<div class="rowitem"><span class="rank">{index:02d}</span>{thumb}'
            f'<span class="body"><a class="t" href="{esc(row["pdp_url"])}" '
            f'target="_blank" rel="noopener">{esc(row["title"])}</a>'
            f'<span class="s">{esc(sub)}</span></span>'
            f'<span class="num"><span class="a">{money(row["revenue"])}</span>'
            f'<span class="b">{short(row["units"])} units {badge}{flags}</span></span></div>'
        )
    return "".join(items)


def _videos(conn: sqlite3.Connection, day: str | None) -> str:
    if not day:
        return _empty(
            "No video panel yet.",
            "Videos arrive with the first detail pull and produce shares one day later.",
        )
    rows = conn.execute(
        """
        SELECT a.*, v.url, v.title, v.author_name, v.cover_image_url, p.title AS product_title
        FROM attribution a
        JOIN video v ON v.item_id = a.item_id
        JOIN product p ON p.product_id = a.product_id
        WHERE a.day = ? AND a.view_delta > 0
        ORDER BY a.view_delta DESC LIMIT 10
        """,
        (day,),
    ).fetchall()
    if not rows:
        return _empty(
            "No view movement on the tracked panel.",
            "Sales on this day, if any, are reported as unattributed rather than assigned.",
        )

    items = []
    for index, row in enumerate(rows, 1):
        thumb = (
            f'<img class="thumb tall" src="{esc(row["cover_image_url"])}" alt="" loading="lazy">'
            if row["cover_image_url"]
            else f'<span class="thumb tall ph">{icon("play", 15)}</span>'
        )
        title = row["title"] or row["product_title"] or "Untitled video"
        handle = f'@{row["author_name"]}' if row["author_name"] else "unknown creator"
        width = max(2.0, min(100.0, row["share"] * 100))
        items.append(
            f'<div class="rowitem"><span class="rank">{index:02d}</span>{thumb}'
            f'<span class="body"><a class="t" href="{esc(row["url"])}" '
            f'target="_blank" rel="noopener">{esc(title)}</a>'
            f'<span class="s">{esc(handle)} · {esc(row["product_title"])}</span>'
            f'<span class="share"><i style="width:{width:.0f}%"></i></span></span>'
            f'<span class="num"><span class="a">+{short(row["view_delta"])}</span>'
            f'<span class="b">{row["share"] * 100:.0f}% share</span></span></div>'
        )
    return "".join(items)


def _health(conn: sqlite3.Connection, day: str | None, credits: int | None) -> str:
    stats = {"Restock flags": 0, "Low confidence": 0, "Provisional": 0, "Unattributed units": 0}
    if day:
        row = conn.execute(
            """
            SELECT SUM(restock) AS restocks,
                   SUM(CASE WHEN confidence < 0.3 THEN 1 ELSE 0 END) AS low,
                   SUM(provisional) AS prov,
                   SUM(unattributed) AS unattr
            FROM daily_result WHERE day = ?
            """,
            (day,),
        ).fetchone()
        stats = {
            "Restock flags": row["restocks"] or 0,
            "Low confidence": row["low"] or 0,
            "Provisional": row["prov"] or 0,
            "Unattributed units": row["unattr"] or 0,
        }

    panel = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='tracked'").fetchone()["n"]
    watch = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='watch'").fetchone()["n"]
    stats["Panel"] = panel
    stats["Watchlist"] = watch
    stats["Credits left"] = credits if credits is not None else "---"

    return "".join(
        f'<div class="u"><span class="k">{esc(k)}</span>'
        f'<span class="v">{esc(v if isinstance(v, str) else f"{v:,}")}</span></div>'
        for k, v in stats.items()
    )


def render(conn: sqlite3.Connection, out_path: Path, credits: int | None = None) -> Path:
    days = _days(conn)
    series = _series(conn, days) if days else {
        k: {"values": [], "money": k == "revenue"}
        for k in ("units", "revenue", "tracked", "attributed", "entrants")
    }
    latest = days[-1] if days else None

    last_run = conn.execute(
        "SELECT * FROM run_log WHERE finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if last_run is None:
        run_pill = '<span class="pill warn"><i class="dot"></i>No run recorded</span>'
    else:
        clean = (last_run["errors"] or 0) == 0
        stamp = last_run["finished_at"][11:16] + " UTC"
        state = "clean" if clean else f'{last_run["errors"]} errors'
        klass = "pill" if clean else "pill warn"
        run_pill = f'<span class="{klass}"><i class="dot"></i>Last run {esc(stamp)} · {esc(state)}</span>'

    if latest:
        headline = f"{short(series['units']['values'][-1])} units · {money(series['revenue']['values'][-1])}"
        day_label = datetime.strptime(latest, "%Y-%m-%d").strftime("%A %d %B %Y")
    else:
        headline = "Waiting on the first delta"
        day_label = "No resolved days yet"

    template = (
        resources.files("shopledger.templates").joinpath("dashboard.html").read_text(encoding="utf-8")
    )
    panel = conn.execute("SELECT COUNT(*) AS n FROM product WHERE tier='tracked'").fetchone()["n"]

    replacements = {
        "__TITLE__": "Shop Ledger",
        "__FOOT__": f"v0.1 · {esc(latest or 'no data')}",
        "__RUNPILL__": run_pill,
        "__CREDITS__": esc(f"{credits:,}") if credits is not None else "---",
        "__DAYLABEL__": esc(day_label),
        "__HEADLINE__": headline,
        "__WINDOW__": f"Last {len(days)} days" if days else "Last 7 days",
        "__PANEL__": esc(panel),
        "__STRIP__": _strip(series),
        "__XFIRST__": esc(days[0] if days else ""),
        "__XLAST__": esc(days[-1] if days else ""),
        "__MOVERS__": _movers(conn, latest),
        "__VIDEOS__": _videos(conn, latest),
        "__HEALTH__": _health(conn, latest, credits),
        "__SERIES__": json.dumps(series, separators=(",", ":")),
        "__WORDMARK__": wordmark(16),
        "__I_HOME__": icon("home"),
        "__I_TRENDING__": icon("trending"),
        "__I_PLAY__": icon("play"),
        "__I_USERS__": icon("users"),
        "__I_PULSE__": icon("pulse"),
        "__I_CAL__": icon("calendar", 14),
        "__I_CHEV__": icon("chevron-down", 14),
        "__I_LAYERS__": icon("layers", 14),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template, encoding="utf-8")
    return out_path
