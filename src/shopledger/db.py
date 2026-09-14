"""SQLite access. Snapshots are append-only; nothing is ever updated in place."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def day_of(iso: str) -> str:
    return iso[:10]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after 0.1.0. Existing databases are migrated in place rather
# than asking anyone to start their history over.
MIGRATIONS: list[tuple[str, str, str]] = [
    ("daily_result", "interval_hours", "REAL"),
    ("daily_result", "partial", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    sql = resources.files("shopledger").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    _migrate(conn)
    conn.commit()
    return conn


@contextmanager
def session(path: Path) -> Iterator[sqlite3.Connection]:
    conn = init(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------- writes


def upsert_product(conn: sqlite3.Connection, row: dict) -> None:
    """Insert a product, or refresh the mutable descriptive fields on an existing one.

    tier and first_seen are deliberately never touched here, so promotion state
    and history survive every sweep.
    """
    conn.execute(
        """
        INSERT INTO product (product_id, title, pdp_url, image_url, seller_id,
                             seller_name, category_id, category_name,
                             first_seen, last_seen, tier)
        VALUES (:product_id, :title, :pdp_url, :image_url, :seller_id,
                :seller_name, :category_id, :category_name,
                :seen, :seen, 'watch')
        ON CONFLICT(product_id) DO UPDATE SET
            title         = excluded.title,
            pdp_url       = excluded.pdp_url,
            image_url     = COALESCE(excluded.image_url, product.image_url),
            seller_name   = COALESCE(excluded.seller_name, product.seller_name),
            category_id   = COALESCE(excluded.category_id, product.category_id),
            category_name = COALESCE(excluded.category_name, product.category_name),
            last_seen     = excluded.last_seen
        """,
        row,
    )


def insert_product_snapshot(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO product_snapshot
            (product_id, captured_at, day, sold_count, stock_total, rating,
             review_count, min_price, max_price, coupon_price, source, raw_json)
        VALUES (:product_id, :captured_at, :day, :sold_count, :stock_total, :rating,
                :review_count, :min_price, :max_price, :coupon_price, :source, :raw_json)
        """,
        row,
    )


def insert_sku_snapshot(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO sku_snapshot
            (product_id, sku_id, captured_at, day, sku_name, price, stock)
        VALUES (:product_id, :sku_id, :captured_at, :day, :sku_name, :price, :stock)
        """,
        rows,
    )


def upsert_video(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO video (item_id, product_id, url, title, author_name, author_url,
                           cover_image_url, upload_time, is_affiliate,
                           first_seen, last_seen, in_panel)
        VALUES (:item_id, :product_id, :url, :title, :author_name, :author_url,
                :cover_image_url, :upload_time, :is_affiliate, :seen, :seen, 1)
        ON CONFLICT(item_id) DO UPDATE SET
            cover_image_url = excluded.cover_image_url,
            title           = COALESCE(excluded.title, video.title),
            is_affiliate    = excluded.is_affiliate,
            last_seen       = excluded.last_seen,
            in_panel        = 1
        """,
        row,
    )


def insert_video_snapshot(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO video_snapshot
            (item_id, captured_at, day, play_count, like_count)
        VALUES (:item_id, :captured_at, :day, :play_count, :like_count)
        """,
        rows,
    )


def set_tier(conn: sqlite3.Connection, product_ids: list[str], tier: str) -> None:
    conn.executemany(
        "UPDATE product SET tier = ? WHERE product_id = ?",
        [(tier, pid) for pid in product_ids],
    )


def mark_panel_absence(conn: sqlite3.Connection, product_id: str, seen_ids: list[str]) -> None:
    """Flag videos that have dropped out of a product's top-18 response."""
    placeholders = ",".join("?" for _ in seen_ids) or "''"
    conn.execute(
        f"UPDATE video SET in_panel = 0 WHERE product_id = ? AND item_id NOT IN ({placeholders})",
        [product_id, *seen_ids],
    )


def start_run(conn: sqlite3.Connection, run_id: str, stage: str, credits: int | None) -> None:
    conn.execute(
        "INSERT INTO run_log (run_id, started_at, stage, credits_before) VALUES (?,?,?,?)",
        (run_id, now_iso(), stage, credits),
    )


def finish_run(
    conn: sqlite3.Connection, run_id: str, credits: int | None, calls: int, errors: int, note: str
) -> None:
    conn.execute(
        "UPDATE run_log SET finished_at=?, credits_after=?, calls=?, errors=?, note=? "
        "WHERE run_id=?",
        (now_iso(), credits, calls, errors, note, run_id),
    )


# ---------------------------------------------------------------- reads


def tracked_products(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM product WHERE tier = 'tracked' ORDER BY last_seen DESC"
    ).fetchall()


def latest_two_snapshots(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM product_snapshot
        WHERE product_id = ? AND source = 'detail'
        ORDER BY captured_at DESC LIMIT 2
        """,
        (product_id,),
    ).fetchall()


def skus_at(conn: sqlite3.Connection, product_id: str, captured_at: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sku_snapshot WHERE product_id = ? AND captured_at = ?",
        (product_id, captured_at),
    ).fetchall()


def videos_for(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM video WHERE product_id = ?", (product_id,)).fetchall()


def video_pair(conn: sqlite3.Connection, item_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM video_snapshot WHERE item_id = ? ORDER BY captured_at DESC LIMIT 2",
        (item_id,),
    ).fetchall()


def orphan_videos(conn: sqlite3.Connection, window_days: int) -> list[sqlite3.Row]:
    """Affiliate videos that fell out of a product's top 18 but are still in window.

    Without this the panel silently shrinks and attribution history breaks: a
    video slipping to 19th reads identically to a video that stopped existing.
    """
    return conn.execute(
        """
        SELECT * FROM video
        WHERE in_panel = 0
          AND is_affiliate = 1
          AND julianday('now') - julianday(last_seen) <= ?
        ORDER BY last_seen DESC
        """,
        (window_days,),
    ).fetchall()


def touch_video(conn: sqlite3.Connection, item_id: str, seen: str) -> None:
    conn.execute("UPDATE video SET last_seen = ? WHERE item_id = ?", (seen, item_id))


def views_per_unit_history(conn: sqlite3.Connection, product_id: str) -> list[float]:
    """Historical views-per-unit for a product, used to calibrate confidence."""
    rows = conn.execute(
        """
        SELECT r.units AS units, SUM(a.view_delta) AS views
        FROM daily_result r
        JOIN attribution a ON a.product_id = r.product_id AND a.day = r.day
        WHERE r.product_id = ? AND r.units > 0
        GROUP BY r.day
        ORDER BY r.day DESC LIMIT 14
        """,
        (product_id,),
    ).fetchall()
    return [row["views"] / row["units"] for row in rows if row["views"] and row["units"]]
