"""Tests for seeding the reject ledger.

The stagger is the only thing worth testing here: it decides whether the
first week of re-checks is spread out or lands as one 17-minute run.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import importlib

seed_rejects = importlib.import_module("seed-rejects")


class TestStagger(unittest.TestCase):
    """Tests the backdating of a seeded row, by hashing repository names
    and asserting on the range and the spread of what comes out."""

    SPAN = 7 * 86400

    def test_an_offset_stays_inside_the_span(self):
        # A row backdated further than the cadence would fall due
        # immediately, which is the pile-up the seeding exists to avoid.
        for i in range(200):
            offset = seed_rejects.stagger(f"owner/repo-{i}", self.SPAN)
            self.assertGreaterEqual(offset, 0)
            self.assertLess(offset, self.SPAN)

    def test_the_same_repository_gets_the_same_offset(self):
        # Re-running the seed on a repaired ledger must not reshuffle it.
        self.assertEqual(
            seed_rejects.stagger("nix-community/disko", self.SPAN),
            seed_rejects.stagger("nix-community/disko", self.SPAN),
        )

    def test_offsets_spread_across_the_span(self):
        # Every day of the cadence should get some of the work. With 700
        # repositories over 7 days, an empty day means the hash is not
        # spreading them and one run pays for the lot.
        days = {
            seed_rejects.stagger(f"owner/repo-{i}", self.SPAN) // 86400
            for i in range(700)
        }
        self.assertEqual(days, set(range(7)))


class TestSpanSeconds(unittest.TestCase):
    """Tests the cadence a ledger implies, from its size and how many rows
    a run re-checks."""

    def test_the_cadence_is_the_ledger_over_the_run_size(self):
        # 8,400 rows at 1,200 a run is a week of daily runs.
        self.assertEqual(seed_rejects.span_seconds(8400, 1200), 7 * 86400)

    def test_a_partial_run_still_counts_as_a_day(self):
        self.assertEqual(seed_rejects.span_seconds(8401, 1200), 8 * 86400)

    def test_a_ledger_smaller_than_one_run_is_a_single_day(self):
        # Never zero: the offset is taken modulo this.
        self.assertEqual(seed_rejects.span_seconds(10, 1200), 86400)

    def test_a_disabled_recheck_still_gives_a_usable_span(self):
        # --recheck-oldest 0 turns the re-checks off; the seed must not
        # divide by it.
        self.assertEqual(seed_rejects.span_seconds(8400, 0), 86400)


if __name__ == "__main__":
    unittest.main()
