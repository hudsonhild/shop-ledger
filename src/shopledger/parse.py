"""Normalise TikTok Shop API payloads into flat rows.

TikTok reshapes response bodies without notice, so every accessor here is
defensive and every snapshot keeps its raw JSON. A parser change can then be
replayed over stored history instead of costing a refetch.
"""

from __future__ import annotations

import json
import re
from typing import Any

_MONEY = re.compile(r"-?\d+(?:\.\d+)?")


def money(value: Any) -> float | None:
    """Pull a number out of 5.99, '5.99', '$55.50' or '$18.70 - 55.50' (takes the first)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _MONEY.search(str(value))
    return float(match.group()) if match else None


def integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = _MONEY.search(str(value))
    return int(float(match.group())) if match else None


def dig(payload: Any, *path: str | int, default: Any = None) -> Any:
    """Walk a nested structure, returning default the moment a step is missing."""
    current = payload
    for step in path:
        if isinstance(step, int):
            if not isinstance(current, list) or len(current) <= step:
                return default
            current = current[step]
        else:
            if not isinstance(current, dict) or step not in current:
                return default
            current = current[step]
    return default if current is None else current


def first_url(node: Any) -> str | None:
    urls = dig(node, "url_list", default=None)
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return None


# --------------------------------------------------------------- shop search


def search_product(raw: dict) -> dict | None:
    """One row from /v1/tiktok/shop/search."""
    product_id = raw.get("product_id")
    if not product_id:
        return None
    canonical = dig(raw, "seo_url", "canonical_url")
    return {
        "product_id": str(product_id),
        "title": str(raw.get("title") or "").strip() or f"Product {product_id}",
        "pdp_url": canonical or f"https://www.tiktok.com/shop/pdp/{product_id}",
        "image_url": first_url(raw.get("image")),
        "seller_id": dig(raw, "seller_info", "seller_id"),
        "seller_name": dig(raw, "seller_info", "shop_name"),
        "category_id": None,
        "category_name": None,
        "sold_count": integer(dig(raw, "sold_info", "sold_count")),
        "price": money(dig(raw, "product_price_info", "sale_price_decimal")),
    }


# ------------------------------------------------------------ product detail


def _da_info(payload: dict) -> dict:
    raw = payload.get("da_info")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def product_detail(payload: dict) -> dict:
    """Flatten /v1/tiktok/product into the product, snapshot, SKU and video rows."""
    product_id = str(payload.get("product_id") or "")
    base = payload.get("product_base") or {}
    da = _da_info(payload)

    skus: list[dict] = []
    for sku in payload.get("skus") or []:
        sku_id = sku.get("sku_id")
        if not sku_id:
            continue
        price = (
            money(dig(sku, "price", "real_price", "price_val"))
            or money(dig(sku, "price", "real_price", "price_str"))
            or money(dig(sku, "price_v2", 0, "min_price", "sale_price_decimal"))
        )
        skus.append(
            {
                "sku_id": str(sku_id),
                "sku_name": sku.get("sku_name"),
                "price": price,
                "stock": integer(sku.get("stock")),
            }
        )

    stock_total = sum(s["stock"] for s in skus if s["stock"] is not None) or None
    if stock_total is None:
        stock_total = integer(da.get("open_stock_cnt"))

    videos: list[dict] = []
    for item in payload.get("related_videos") or []:
        item_id = item.get("item_id")
        if not item_id:
            continue
        videos.append(
            {
                "item_id": str(item_id),
                "url": item.get("url") or "",
                "title": (item.get("title") or "").strip() or None,
                "author_name": item.get("author_name"),
                "author_url": item.get("author_url"),
                "author_id": str(item.get("author_id") or ""),
                "cover_image_url": item.get("cover_image_url"),
                "upload_time": str(item.get("upload_time") or "") or None,
                "is_affiliate": 1 if item.get("bc_ad_label_text") else 0,
                "play_count": integer(item.get("play_count")) or 0,
                "like_count": integer(item.get("like_count")) or 0,
            }
        )

    return {
        "product": {
            "product_id": product_id,
            "title": str(base.get("title") or "").strip() or f"Product {product_id}",
            "pdp_url": f"https://www.tiktok.com/shop/pdp/{product_id}",
            "image_url": first_url(dig(base, "images", 0, default={})),
            "seller_id": str(payload.get("seller_id") or "") or None,
            "seller_name": dig(payload, "seller", "name"),
            "category_id": str(base.get("category_id") or "") or None,
            "category_name": base.get("category_name"),
        },
        "snapshot": {
            "sold_count": integer(base.get("sold_count")) or integer(da.get("volume")),
            "stock_total": stock_total,
            "rating": money(dig(payload, "product_detail_review", "product_rating")),
            "review_count": integer(dig(payload, "product_detail_review", "review_count")),
            "min_price": money(dig(base, "price", "min_sku_price")),
            "max_price": money(dig(base, "price", "max_sku_price")),
            "coupon_price": money(da.get("sale_price_after_coupon")),
        },
        "skus": skus,
        "videos": videos,
    }
