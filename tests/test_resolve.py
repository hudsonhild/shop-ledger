"""The reconciliation and attribution rules are the whole product. Pin them."""

from __future__ import annotations

import unittest

from shopledger.resolve import attribute, compute_units


def skus(*rows):
    return {
        sku_id: {"sku_id": sku_id, "stock": stock, "price": price} for sku_id, stock, price in rows
    }


class ComputeUnits(unittest.TestCase):
    def test_per_sku_revenue_beats_a_price_midpoint(self):
        """The cheap variant moving must not be priced as the expensive one."""
        prev = skus(("a", 100, 5.99), ("b", 100, 18.99))
        curr = skus(("a", 90, 5.99), ("b", 100, 18.99))
        result = compute_units(prev, curr, 1000, 1010)

        self.assertEqual(result.units, 10)
        self.assertEqual(result.method, "sku_stock")
        self.assertAlmostEqual(result.revenue, 59.90, places=2)
        # A midpoint of the 5.99-18.99 range would have claimed ~124.90.

    def test_restock_falls_back_to_the_sold_counter(self):
        prev = skus(("a", 10, 20.0))
        curr = skus(("a", 500, 20.0))
        result = compute_units(prev, curr, 1000, 1040)

        self.assertTrue(result.restock)
        self.assertEqual(result.method, "sold_delta")
        self.assertEqual(result.units, 40)

    def test_disagreement_beyond_tolerance_takes_the_conservative_figure(self):
        prev = skus(("a", 1000, 10.0))
        curr = skus(("a", 900, 10.0))  # stock says 100
        result = compute_units(prev, curr, 5000, 5400)  # sold says 400

        self.assertEqual(result.method, "reconciled")
        self.assertEqual(result.units, 100)
        self.assertEqual(result.sold_delta, 400)
        self.assertEqual(result.stock_delta, 100)

    def test_small_disagreement_is_within_tolerance(self):
        prev = skus(("a", 1000, 10.0))
        curr = skus(("a", 900, 10.0))
        result = compute_units(prev, curr, 5000, 5103)

        self.assertEqual(result.method, "sku_stock")
        self.assertEqual(result.units, 100)

    def test_hidden_stock_uses_the_sold_counter(self):
        result = compute_units({}, {}, 1000, 1025)
        self.assertEqual(result.method, "sold_delta")
        self.assertEqual(result.units, 25)

    def test_a_genuine_zero_day_is_recorded_not_dropped(self):
        prev = skus(("a", 100, 10.0))
        curr = skus(("a", 100, 10.0))
        result = compute_units(prev, curr, 1000, 1000)

        self.assertEqual(result.units, 0)
        self.assertEqual(result.method, "reconciled")
        self.assertEqual(result.revenue, 0.0)

    def test_no_data_at_all(self):
        result = compute_units({}, {}, None, None)
        self.assertEqual(result.method, "no_data")
        self.assertEqual(result.units, 0)


class Attribute(unittest.TestCase):
    def _videos(self):
        return [
            {"item_id": "v1", "view_delta": 900_000, "play_count": 9_000_000, "like_count": 90_000},
            {"item_id": "v2", "view_delta": 100_000, "play_count": 1_000_000, "like_count": 10_000},
        ]

    def test_shares_track_view_delta(self):
        result = attribute(500, 5000.0, self._videos(), [2000.0] * 3, 2000, 0)
        shares = {row["item_id"]: row["share"] for row in result.rows}

        self.assertAlmostEqual(shares["v1"], 0.9, places=3)
        self.assertAlmostEqual(shares["v2"], 0.1, places=3)

    def test_engagement_weighting_favours_the_higher_like_rate(self):
        videos = [
            # Same view delta, very different like rates.
            {
                "item_id": "farm",
                "view_delta": 100_000,
                "play_count": 10_000_000,
                "like_count": 1_000,
            },
            {"item_id": "real", "view_delta": 100_000, "play_count": 200_000, "like_count": 12_000},
        ]
        result = attribute(100, 1000.0, videos, [1000.0] * 3, 1000, 10)
        shares = {row["item_id"]: row["share"] for row in result.rows}

        self.assertGreater(shares["real"], shares["farm"])

    def test_no_view_movement_means_everything_is_unattributed(self):
        videos = [{"item_id": "v1", "view_delta": 0, "play_count": 500, "like_count": 5}]
        result = attribute(300, 3000.0, videos, [], 2000, 10)

        self.assertEqual(result.rows, [])
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.unattributed, 300)

    def test_attribution_never_exceeds_the_days_units(self):
        """A huge view spike must not attribute more units than were actually sold."""
        videos = [
            {"item_id": "v1", "view_delta": 50_000_000, "play_count": 50_000_000, "like_count": 0}
        ]
        result = attribute(10, 100.0, videos, [2000.0] * 3, 2000, 10)

        self.assertLessEqual(result.confidence, 1.0)
        self.assertLessEqual(sum(row["units"] for row in result.rows), 10.0001)

    def test_thin_coverage_leaves_a_residual(self):
        """Panel explains a fraction of the day, so most of it stays unattributed."""
        videos = [{"item_id": "v1", "view_delta": 20_000, "play_count": 100_000, "like_count": 0}]
        result = attribute(100, 1000.0, videos, [2000.0] * 3, 2000, 0)

        self.assertAlmostEqual(result.confidence, 0.1, places=3)
        self.assertEqual(result.unattributed, 90)

    def test_no_history_marks_the_row_provisional(self):
        result = attribute(100, 1000.0, self._videos(), [], 2000, 10)
        self.assertTrue(result.provisional)

    def test_enough_history_is_not_provisional(self):
        result = attribute(100, 1000.0, self._videos(), [1500.0, 2500.0, 2000.0], 2000, 10)
        self.assertFalse(result.provisional)


if __name__ == "__main__":
    unittest.main()
