"""The site must render from an empty database and from a populated one.

Day one genuinely has no deltas, so the empty path is the normal first
experience and is worth pinning.
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from shopledger import db, render


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO product (product_id, title, pdp_url, image_url, seller_name, "
        "category_name, first_seen, last_seen, tier) VALUES "
        "('p1','Test Serum','https://www.tiktok.com/shop/pdp/p1',NULL,'A Shop','Beauty',"
        "'2026-09-13T00:00:00+00:00','2026-09-14T00:00:00+00:00','tracked')"
    )
    conn.execute(
        "INSERT INTO daily_result (product_id, day, units, revenue, method, confidence, "
        "restock, provisional, unattributed, sold_delta, stock_delta) "
        "VALUES ('p1','2026-09-14',120,1440.0,'sku_stock',0.72,0,0,34,120,120)"
    )
    conn.execute(
        "INSERT INTO video (item_id, product_id, url, title, author_name, author_url, "
        "cover_image_url, upload_time, is_affiliate, first_seen, last_seen, in_panel) VALUES "
        "('v1','p1','https://www.tiktok.com/@creator/video/v1','Demo','creator',"
        "'https://www.tiktok.com/@creator',NULL,NULL,1,"
        "'2026-09-13T00:00:00+00:00','2026-09-14T00:00:00+00:00',1)"
    )
    conn.execute(
        "INSERT INTO attribution (product_id, item_id, day, view_delta, share, units, revenue) "
        "VALUES ('p1','v1','2026-09-14',50000,0.8,96.0,1152.0)"
    )
    conn.execute(
        "INSERT INTO sku_snapshot (product_id, sku_id, captured_at, day, sku_name, price, stock) "
        "VALUES ('p1','s1','2026-09-14T02:00:00+00:00','2026-09-14','30ml',12.0,900)"
    )
    conn.commit()


class RenderSite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.conn = db.init(self.root / "test.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _render(self):
        out = self.root / "out"
        render.render(self.conn, out, credits=8600)
        return out

    def test_renders_from_an_empty_database(self):
        out = self._render()
        for name in ("index.html", "products.html", "videos.html", "creators.html", "health.html"):
            page = out / name
            self.assertTrue(page.exists(), f"{name} missing")
            text = page.read_text()
            self.assertNotIn("__", text.split("<style>")[0], "unreplaced token in the head")
            self.assertIn("<title>", text)

    def test_empty_index_says_why_it_is_blank(self):
        text = (self._render() / "index.html").read_text()
        self.assertIn("Waiting on the first delta", text)
        self.assertIn("a delta needs two readings", text)

    def test_populated_site_renders_every_page_and_the_product_detail(self):
        _seed(self.conn)
        out = self._render()
        self.assertTrue((out / "products" / "p1.html").exists())
        index = (out / "index.html").read_text()
        self.assertIn("Test Serum", index)
        self.assertIn("https://www.tiktok.com/@creator/video/v1", index)

    def test_no_unreplaced_tokens_anywhere(self):
        _seed(self.conn)
        out = self._render()
        for page in out.rglob("*.html"):
            leftovers = re.findall(r"__[A-Z_]+__", page.read_text())
            self.assertEqual(leftovers, [], f"{page.name} has {leftovers}")

    def test_every_internal_link_resolves(self):
        _seed(self.conn)
        out = self._render()
        checked = 0
        for page in out.rglob("*.html"):
            for href in re.findall(r'href="([^"#:]+\.html[^"]*)"', page.read_text()):
                target = (page.parent / href.split("#")[0]).resolve()
                self.assertTrue(target.exists(), f"{page.name} -> {href} is broken")
                checked += 1
        self.assertGreater(checked, 0)

    def test_unattributed_units_are_shown_not_hidden(self):
        _seed(self.conn)
        text = (self._render() / "health.html").read_text()
        self.assertIn("Unattributed units", text)
        self.assertIn("34", text)

    def test_tolerates_being_handed_a_file_path(self):
        out = self.root / "out" / "index.html"
        render.render(self.conn, out, credits=None)
        self.assertTrue((self.root / "out" / "products.html").exists())


if __name__ == "__main__":
    unittest.main()
