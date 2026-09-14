"""Parsing is defensive on purpose: TikTok reshapes payloads without notice."""

from __future__ import annotations

import unittest

from shopledger.parse import dig, integer, money, product_detail, search_product, video_stats

# Trimmed from a real /v1/tiktok/product response, 14 September 2026.
DETAIL = {
    "product_id": "1729407540442862434",
    "product_base": {
        "title": "Wonderskin Lip Stain Masque",
        "sold_count": 689116,
        "category_id": 601450,
        "category_name": "Beauty & Personal Care",
        "images": [{"url_list": ["https://cdn.example/img.webp"]}],
        "price": {"min_sku_price": "18.70", "max_sku_price": "55.50", "real_price": "$18.70 - 55.50"},
    },
    "seller": {"name": "Wonderskin", "rating": 4.8},
    "seller_id": "7494697002145646021",
    "product_detail_review": {"product_rating": 4.9, "review_count": 2311},
    "da_info": '{"volume":689116,"open_stock_cnt":658454,"sale_price_after_coupon":"2.99"}',
    "skus": [
        {
            "sku_id": "s1",
            "sku_name": "Whimsical",
            "stock": 11283,
            "price": {"real_price": {"price_val": "55.5", "price_str": "$55.50"}},
        },
        {
            "sku_id": "s2",
            "sku_name": "Bundle",
            "stock": 262041,
            "price_v2": [{"min_price": {"sale_price_decimal": "18.7"}}],
        },
    ],
    "related_videos": [
        {
            "item_id": "7398692658459282734",
            "play_count": "31864931",
            "like_count": "1190040",
            "upload_time": "1722642381",
            "title": "SHADE WHIMSICAL And it wont move",
            "author_name": "carlyxspam",
            "author_id": "192290848842432512",
            "bc_ad_label_text": "Creator earns commission",
            "url": "https://www.tiktok.com/@192290848842432512/video/7398692658459282734",
            "author_url": "https://www.tiktok.com/@192290848842432512",
            "cover_image_url": "https://cdn.example/cover.jpeg",
        },
        {
            "item_id": "organic1",
            "play_count": 1200,
            "like_count": 30,
            "url": "https://www.tiktok.com/@x/video/organic1",
        },
    ],
}


class Helpers(unittest.TestCase):
    def test_money_handles_every_shape_seen_in_the_wild(self):
        self.assertEqual(money(5.99), 5.99)
        self.assertEqual(money("5.99"), 5.99)
        self.assertEqual(money("$55.50"), 55.5)
        self.assertEqual(money("$18.70 - 55.50"), 18.70)
        self.assertIsNone(money(None))
        self.assertIsNone(money(""))

    def test_integer_tolerates_strings(self):
        self.assertEqual(integer("31864931"), 31864931)
        self.assertEqual(integer(46), 46)
        self.assertIsNone(integer(None))

    def test_dig_returns_default_on_a_missing_step(self):
        self.assertEqual(dig({"a": {"b": 1}}, "a", "b"), 1)
        self.assertIsNone(dig({"a": {}}, "a", "b"))
        self.assertEqual(dig({}, "a", "b", "c", default="x"), "x")
        self.assertEqual(dig({"a": []}, "a", 0, default="x"), "x")


class ProductDetail(unittest.TestCase):
    def setUp(self):
        self.parsed = product_detail(DETAIL)

    def test_sku_prices_come_from_either_shape(self):
        prices = {s["sku_id"]: s["price"] for s in self.parsed["skus"]}
        self.assertEqual(prices["s1"], 55.5)
        self.assertEqual(prices["s2"], 18.7)

    def test_stock_total_sums_the_variants(self):
        self.assertEqual(self.parsed["snapshot"]["stock_total"], 11283 + 262041)

    def test_affiliate_flag_is_read_from_the_commission_label(self):
        flags = {v["item_id"]: v["is_affiliate"] for v in self.parsed["videos"]}
        self.assertEqual(flags["7398692658459282734"], 1)
        self.assertEqual(flags["organic1"], 0)

    def test_video_urls_are_preserved_verbatim(self):
        video = self.parsed["videos"][0]
        self.assertEqual(
            video["url"], "https://www.tiktok.com/@192290848842432512/video/7398692658459282734"
        )
        self.assertEqual(video["play_count"], 31864931)

    def test_coupon_price_is_lifted_from_the_da_info_json_string(self):
        self.assertEqual(self.parsed["snapshot"]["coupon_price"], 2.99)

    def test_survives_a_completely_empty_payload(self):
        parsed = product_detail({})
        self.assertEqual(parsed["skus"], [])
        self.assertEqual(parsed["videos"], [])
        self.assertIsNone(parsed["snapshot"]["sold_count"])


class SearchProduct(unittest.TestCase):
    def test_reads_a_search_row(self):
        row = search_product(
            {
                "product_id": "123",
                "title": "Avocado Keratin Hair Oil",
                "sold_info": {"sold_count": 46},
                "product_price_info": {"sale_price_decimal": 5.99},
                "seller_info": {"seller_id": "s9", "shop_name": "Bloom Muse"},
                "image": {"url_list": ["https://cdn.example/a.webp"]},
                "seo_url": {"canonical_url": "https://www.tiktok.com/shop/pdp/123"},
            }
        )
        self.assertEqual(row["sold_count"], 46)
        self.assertEqual(row["price"], 5.99)
        self.assertEqual(row["pdp_url"], "https://www.tiktok.com/shop/pdp/123")

    def test_rejects_a_row_with_no_id(self):
        self.assertIsNone(search_product({"title": "nope"}))

    def test_falls_back_to_a_constructed_pdp_url(self):
        row = search_product({"product_id": "99"})
        self.assertEqual(row["pdp_url"], "https://www.tiktok.com/shop/pdp/99")



class VideoStats(unittest.TestCase):
    """Likes live under digg_count on /v2/tiktok/video, not like_count."""

    def test_reads_statistics(self):
        stats = video_stats(
            {"aweme_detail": {"statistics": {"play_count": 31865405, "digg_count": 1190044}}}
        )
        self.assertEqual(stats, {"play_count": 31865405, "like_count": 1190044})

    def test_returns_none_when_statistics_are_missing(self):
        self.assertIsNone(video_stats({}))
        self.assertIsNone(video_stats({"aweme_detail": {}}))
        self.assertIsNone(video_stats({"aweme_detail": {"statistics": {"digg_count": 5}}}))


if __name__ == "__main__":
    unittest.main()
