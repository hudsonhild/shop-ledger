"""Tracked-tier detail pull. One credit per product per day.

This is where SKU stock, SKU price and the related-video panel enter the
database. Everything downstream is local computation over what lands here.
"""

from __future__ import annotations

import json
import sqlite3

from . import db
from .client import ApiError, Client, NotFound, OutOfCredits
from .parse import product_detail, video_stats


def pull(conn: sqlite3.Connection, client: Client, min_credits: int) -> dict:
    products = db.tracked_products(conn)
    captured_at = db.now_iso()
    day = db.day_of(captured_at)

    pulled = 0
    videos_seen = 0
    missing: list[str] = []
    failures: list[str] = []

    for product in products:
        if client.credits is not None and client.credits < min_credits:
            raise OutOfCredits(
                f"Stopping at {client.credits} credits, below the {min_credits} floor. "
                f"{pulled} of {len(products)} products pulled; this day was not written."
            )

        product_id = product["product_id"]
        try:
            payload = client.product(product_id)
        except NotFound:
            missing.append(product_id)
            continue
        except OutOfCredits:
            raise
        except ApiError as exc:
            failures.append(f"{product_id}: {exc}")
            continue

        parsed = product_detail(payload)
        db.upsert_product(conn, {**parsed["product"], "seen": captured_at})
        db.insert_product_snapshot(
            conn,
            {
                "product_id": product_id,
                "captured_at": captured_at,
                "day": day,
                **parsed["snapshot"],
                "source": "detail",
                "raw_json": json.dumps(payload, separators=(",", ":")),
            },
        )

        if parsed["skus"]:
            db.insert_sku_snapshot(
                conn,
                [
                    {**sku, "product_id": product_id, "captured_at": captured_at, "day": day}
                    for sku in parsed["skus"]
                ],
            )

        video_ids = []
        video_snaps = []
        for video in parsed["videos"]:
            video_ids.append(video["item_id"])
            db.upsert_video(
                conn,
                {
                    "item_id": video["item_id"],
                    "product_id": product_id,
                    "url": video["url"],
                    "title": video["title"],
                    "author_name": video["author_name"],
                    "author_url": video["author_url"],
                    "cover_image_url": video["cover_image_url"],
                    "upload_time": video["upload_time"],
                    "is_affiliate": video["is_affiliate"],
                    "seen": captured_at,
                },
            )
            video_snaps.append(
                {
                    "item_id": video["item_id"],
                    "captured_at": captured_at,
                    "day": day,
                    "play_count": video["play_count"],
                    "like_count": video["like_count"],
                }
            )

        if video_snaps:
            db.insert_video_snapshot(conn, video_snaps)
        db.mark_panel_absence(conn, product_id, video_ids)

        videos_seen += len(video_ids)
        pulled += 1

    return {
        "pulled": pulled,
        "of": len(products),
        "videos": videos_seen,
        "missing": missing,
        "failures": failures,
    }


def persist_panel(conn, client: Client, window_days: int, min_credits: int, budget: int) -> dict:
    """Keep sampling affiliate videos that fell out of a product's top 18.

    `related_videos` is ranked and truncated, so a video slipping to 19th
    disappears from the response and a naive pipeline reads that as the video
    ceasing to exist. Once an item is in the database it keeps its history for
    as long as it stays inside the attribution window, so the panel only grows.

    Capped by `budget` so a long tail of orphans cannot quietly eat the credit
    balance the tracked panel needs tomorrow.
    """
    orphans = db.orphan_videos(conn, window_days)[:budget]
    captured_at = db.now_iso()
    day = db.day_of(captured_at)

    kept = 0
    gone: list[str] = []
    rows: list[dict] = []

    for video in orphans:
        if client.credits is not None and client.credits < min_credits:
            break
        try:
            payload = client.video(video["url"])
        except NotFound:
            gone.append(video["item_id"])
            continue
        except OutOfCredits:
            break
        except ApiError:
            continue

        stats = video_stats(payload)
        if stats is None:
            continue
        rows.append({"item_id": video["item_id"], "captured_at": captured_at, "day": day, **stats})
        db.touch_video(conn, video["item_id"], captured_at)
        kept += 1

    if rows:
        db.insert_video_snapshot(conn, rows)

    return {"orphans": len(orphans), "kept": kept, "gone": len(gone)}
