"""Turn consecutive snapshots into units, revenue and attribution.

Pure computation over what is already stored, so it costs nothing to re-run and
can be replayed across the whole history after a modelling change.

The two rules that matter:
  1. Revenue is summed per SKU, never taken from the midpoint of a price range.
  2. Attribution is never forced to total 100%. When the video panel cannot
     explain the day, the remainder is reported as unattributed rather than
     smeared across whichever video happened to move.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from statistics import median

from . import db
from .config import Config


@dataclass
class Units:
    units: int = 0
    revenue: float = 0.0
    method: str = "no_data"
    restock: bool = False
    sold_delta: int | None = None
    stock_delta: int | None = None
    per_sku: dict[str, int] = field(default_factory=dict)


def compute_units(
    prev_skus: dict[str, dict],
    curr_skus: dict[str, dict],
    prev_sold: int | None,
    curr_sold: int | None,
) -> Units:
    """Reconcile the two independent unit counts, because each fails differently."""
    per_sku: dict[str, int] = {}
    restock = False
    for sku_id, curr in curr_skus.items():
        prev = prev_skus.get(sku_id)
        if prev is None or prev.get("stock") is None or curr.get("stock") is None:
            continue
        delta = prev["stock"] - curr["stock"]
        if delta < 0:
            restock = True
        elif delta > 0:
            per_sku[sku_id] = delta

    stock_delta = sum(per_sku.values()) if per_sku else 0
    sold_delta = (
        curr_sold - prev_sold if curr_sold is not None and prev_sold is not None else None
    )

    result = Units(
        restock=restock,
        sold_delta=sold_delta,
        stock_delta=stock_delta if curr_skus else None,
        per_sku=per_sku,
    )

    if restock:
        # A restock makes the stock delta meaningless for this day.
        result.units = max(0, sold_delta or 0)
        result.method = "sold_delta"
    elif stock_delta > 0 and sold_delta is not None and sold_delta > 0:
        tolerance = max(5.0, 0.10 * max(stock_delta, sold_delta))
        if abs(stock_delta - sold_delta) <= tolerance:
            result.units = stock_delta
            result.method = "sku_stock"
        else:
            # They disagree beyond tolerance. Take the conservative figure and
            # keep both numbers on the row so the gap stays auditable.
            result.units = min(stock_delta, sold_delta)
            result.method = "reconciled"
    elif stock_delta > 0:
        result.units = stock_delta
        result.method = "sku_stock"
    elif sold_delta is not None and sold_delta > 0:
        # Stock hidden, unchanged, or stale. The sold counter is all there is.
        result.units = sold_delta
        result.method = "sold_delta"
    elif sold_delta is not None or curr_skus:
        result.units = 0
        result.method = "reconciled"

    result.revenue = _revenue(result, curr_skus)
    return result


def _revenue(result: Units, curr_skus: dict[str, dict]) -> float:
    if result.units <= 0:
        return 0.0

    priced = {
        sku_id: sku for sku_id, sku in curr_skus.items() if sku.get("price") is not None
    }
    if not priced:
        return 0.0

    if result.per_sku:
        exact = sum(
            units * priced[sku_id]["price"]
            for sku_id, units in result.per_sku.items()
            if sku_id in priced
        )
        counted = sum(u for s, u in result.per_sku.items() if s in priced)
        if counted > 0:
            # Scale when the chosen unit figure differs from the stock delta,
            # keeping the observed variant mix.
            return exact * (result.units / counted)

    # No per-variant movement to lean on. Weight by stock share so the common
    # variant dominates, which still beats a midpoint of the price range.
    weights = [(s["price"], s.get("stock") or 0) for s in priced.values()]
    total_stock = sum(w for _, w in weights)
    if total_stock > 0:
        avg = sum(price * w for price, w in weights) / total_stock
    else:
        avg = sum(price for price, _ in weights) / len(weights)
    return result.units * avg


@dataclass
class Attribution:
    confidence: float = 0.0
    provisional: bool = False
    unattributed: int = 0
    rows: list[dict] = field(default_factory=list)


def attribute(
    units: int,
    revenue: float,
    videos: list[dict],
    vpu_history: list[float],
    default_vpu: float,
    engagement_k: float,
) -> Attribution:
    """Apportion a day's sales across the videos that plausibly caused them.

    `videos` carries dicts of item_id, view_delta, play_count, like_count.
    """
    movers = [v for v in videos if v["view_delta"] > 0]
    result = Attribution()

    if units <= 0 or not movers:
        result.unattributed = max(0, units)
        return result

    total_views = sum(v["view_delta"] for v in movers)

    if len(vpu_history) >= 3:
        vpu = median(vpu_history)
    else:
        vpu = default_vpu
        result.provisional = True
    vpu = max(vpu, 1.0)

    predicted_units = total_views / vpu
    result.confidence = max(0.0, min(1.0, predicted_units / units))

    weighted = []
    for video in movers:
        plays = video.get("play_count") or 0
        likes = video.get("like_count") or 0
        like_rate = (likes / plays) if plays > 0 else 0.0
        weighted.append((video, video["view_delta"] * (1 + engagement_k * like_rate)))

    total_weight = sum(w for _, w in weighted)
    if total_weight <= 0:
        result.unattributed = units
        return result

    assigned = 0.0
    for video, weight in weighted:
        share = weight / total_weight
        unit_share = units * share * result.confidence
        assigned += unit_share
        result.rows.append(
            {
                "item_id": video["item_id"],
                "view_delta": video["view_delta"],
                "share": round(share, 6),
                "units": round(unit_share, 3),
                "revenue": round(revenue * share * result.confidence, 2),
            }
        )

    result.unattributed = max(0, round(units - assigned))
    return result


def resolve(conn: sqlite3.Connection, cfg: Config) -> dict:
    """Resolve every tracked product that has two detail snapshots."""
    written = 0
    skipped = 0
    low_confidence = 0
    restocks = 0

    for product in db.tracked_products(conn):
        product_id = product["product_id"]
        snaps = db.latest_two_snapshots(conn, product_id)
        if len(snaps) < 2:
            skipped += 1
            continue

        curr, prev = snaps[0], snaps[1]
        day = curr["day"]

        curr_skus = {r["sku_id"]: dict(r) for r in db.skus_at(conn, product_id, curr["captured_at"])}
        prev_skus = {r["sku_id"]: dict(r) for r in db.skus_at(conn, product_id, prev["captured_at"])}

        units = compute_units(prev_skus, curr_skus, prev["sold_count"], curr["sold_count"])

        videos = []
        for video in db.videos_for(conn, product_id):
            if not video["is_affiliate"]:
                continue
            pair = db.video_pair(conn, video["item_id"])
            if len(pair) < 2:
                continue
            delta = (pair[0]["play_count"] or 0) - (pair[1]["play_count"] or 0)
            videos.append(
                {
                    "item_id": video["item_id"],
                    "view_delta": max(0, delta),
                    "play_count": pair[0]["play_count"] or 0,
                    "like_count": pair[0]["like_count"] or 0,
                }
            )

        attr = attribute(
            units.units,
            units.revenue,
            videos,
            db.views_per_unit_history(conn, product_id),
            cfg.default_vpu,
            cfg.engagement_k,
        )

        conn.execute(
            """
            INSERT INTO daily_result
                (product_id, day, units, revenue, method, confidence, restock,
                 provisional, unattributed, sold_delta, stock_delta)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(product_id, day) DO UPDATE SET
                units=excluded.units, revenue=excluded.revenue, method=excluded.method,
                confidence=excluded.confidence, restock=excluded.restock,
                provisional=excluded.provisional, unattributed=excluded.unattributed,
                sold_delta=excluded.sold_delta, stock_delta=excluded.stock_delta
            """,
            (
                product_id,
                day,
                units.units,
                round(units.revenue, 2),
                units.method,
                round(attr.confidence, 4),
                int(units.restock),
                int(attr.provisional),
                attr.unattributed,
                units.sold_delta,
                units.stock_delta,
            ),
        )

        for row in attr.rows:
            conn.execute(
                """
                INSERT INTO attribution (product_id, item_id, day, view_delta, share, units, revenue)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(product_id, item_id, day) DO UPDATE SET
                    view_delta=excluded.view_delta, share=excluded.share,
                    units=excluded.units, revenue=excluded.revenue
                """,
                (
                    product_id,
                    row["item_id"],
                    day,
                    row["view_delta"],
                    row["share"],
                    row["units"],
                    row["revenue"],
                ),
            )

        written += 1
        if units.restock:
            restocks += 1
        if attr.confidence < 0.3:
            low_confidence += 1

    return {
        "written": written,
        "skipped": skipped,
        "restocks": restocks,
        "low_confidence": low_confidence,
    }
