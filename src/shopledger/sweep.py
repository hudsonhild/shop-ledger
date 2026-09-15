"""Discovery. Sweep keywords, record what is out there, promote the real movers.

Search already carries a lifetime sold_count, so a candidate accrues the history
needed to compute a delta at no marginal cost. Only promoted products pay for a
detail pull.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path

from . import db
from .client import ApiError, Client


def load_keywords(path: Path | None = None) -> list[str]:
    if path is not None:
        text = path.read_text(encoding="utf-8")
    else:
        text = resources.files("shopledger").joinpath("keywords.txt").read_text(encoding="utf-8")
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def sweep(conn: sqlite3.Connection, client: Client, keywords: list[str]) -> dict:
    """Record one search snapshot per discovered product. One credit per keyword."""
    from .parse import search_product

    captured_at = db.now_iso()
    day = db.day_of(captured_at)
    seen: set[str] = set()
    failures: list[str] = []

    for keyword in keywords:
        try:
            products = client.shop_search(keyword)
        except ApiError as exc:
            failures.append(f"{keyword}: {exc}")
            continue

        for raw in products:
            row = search_product(raw)
            if not row or row["product_id"] in seen:
                continue
            seen.add(row["product_id"])
            db.upsert_product(conn, {**row, "seen": captured_at})
            db.insert_product_snapshot(
                conn,
                {
                    "product_id": row["product_id"],
                    "captured_at": captured_at,
                    "day": day,
                    "sold_count": row["sold_count"],
                    "stock_total": None,
                    "rating": None,
                    "review_count": None,
                    "min_price": row["price"],
                    "max_price": row["price"],
                    "coupon_price": None,
                    "source": "sweep",
                    "raw_json": None,
                },
            )

    return {"keywords": len(keywords), "products": len(seen), "failures": failures}


def promote(conn: sqlite3.Connection, panel_size: int, stale_days: int = 3) -> dict:
    """Rank the watchlist by recent sold_count delta and take the top N into tracked.

    Ranking by movement rather than lifetime volume is the whole point. A product
    that sold 600,000 units over two years is history; one that sold 4,000
    yesterday is a signal.

    Two windows, and they do different jobs. The delta is measured over the last
    ``stale_days`` so it reads as movement rather than history. Eligibility is
    tighter: a product must have come back in the most recent sweep. Without that
    second rule a product the keyword list no longer searches keeps the delta it
    earned before it went quiet and blocks live movers out of the panel forever.
    Editing keywords.txt is exactly when that bites.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=stale_days)).replace(microsecond=0).isoformat()
    row = conn.execute(
        "SELECT MAX(captured_at) AS at FROM product_snapshot WHERE source = 'sweep'"
    ).fetchone()
    last_sweep = (row["at"] if row else None) or cutoff

    rows = conn.execute(
        """
        WITH recent AS (
            SELECT ps.product_id, ps.captured_at, ps.sold_count
            FROM product_snapshot ps
            JOIN product p ON p.product_id = ps.product_id
            WHERE ps.sold_count IS NOT NULL
              AND ps.captured_at >= ?
              AND p.last_seen    >= ?
        ),
        bounds AS (
            SELECT product_id,
                   MIN(captured_at) AS first_at,
                   MAX(captured_at) AS last_at,
                   COUNT(*)         AS n
            FROM recent
            GROUP BY product_id
            HAVING n >= 2
        )
        SELECT b.product_id,
               (SELECT sold_count FROM recent
                 WHERE product_id = b.product_id AND captured_at = b.last_at) -
               (SELECT sold_count FROM recent
                 WHERE product_id = b.product_id AND captured_at = b.first_at) AS delta
        FROM bounds b
        ORDER BY delta DESC
        """,
        (cutoff, last_sweep),
    ).fetchall()

    movers = [row["product_id"] for row in rows if (row["delta"] or 0) > 0][:panel_size]

    if not movers:
        # Cold start: nothing has two snapshots yet, so fall back to the largest
        # sellers just to get the panel moving. These become delta-ranked tomorrow.
        fallback = conn.execute(
            """
            SELECT p.product_id
            FROM product p
            JOIN (SELECT product_id, MAX(sold_count) AS sc
                  FROM product_snapshot
                  WHERE captured_at >= ?
                  GROUP BY product_id) s
              ON s.product_id = p.product_id
            WHERE p.last_seen >= ?
            ORDER BY s.sc DESC LIMIT ?
            """,
            (cutoff, last_sweep, panel_size),
        ).fetchall()
        movers = [row["product_id"] for row in fallback]
        cold = True
    else:
        cold = False

    current = {row["product_id"] for row in db.tracked_products(conn)}
    incoming = set(movers)

    db.set_tier(conn, list(incoming - current), "tracked")
    db.set_tier(conn, list(current - incoming), "watch")

    return {"tracked": len(incoming), "added": len(incoming - current), "cold_start": cold}
