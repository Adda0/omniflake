"""Tests for the pin stage's negative cache.

Both suites work on plain data — a list of failure rows, an error string —
so nothing here runs Nix or touches the network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pin


class TestIsTransient(unittest.TestCase):
    """Tests which errors pin.py is willing to re-attempt, by asserting on
    the marker strings GitHub and Nix actually emit."""

    def test_quota_errors_are_transient(self):
        # 403 is what GitHub returns for exceeded quota. Without it, a
        # rate-limited run records its casualties as permanent and a scoped
        # retry never looks at them again.
        self.assertTrue(pin.is_transient("error: unable to download: HTTP error 403"))
        self.assertTrue(pin.is_transient("API rate limit exceeded for user ID 1"))
        self.assertTrue(pin.is_transient("error: ... HTTP error 429"))

    def test_flake_errors_are_permanent(self):
        # These say something about the flake at that revision, and the
        # revision never changes.
        self.assertFalse(pin.is_transient("error: syntax error, unexpected ':'"))
        self.assertFalse(pin.is_transient("error: ... HTTP error 404"))
        self.assertFalse(pin.is_transient("error: ... HTTP error 422"))


class TestSkipRefs(unittest.TestCase):
    """Tests which recorded failures each retry policy declines to
    re-attempt, over a failures file holding both verdicts and a ref that
    was recorded twice."""

    FAILURES = [
        {"ref": "github:a/permanent/rev1", "transient": False},
        {"ref": "github:b/transient/rev2", "transient": True},
        # Recorded permanent, then re-recorded transient on a later run.
        {"ref": "github:c/changed/rev3", "transient": False},
        {"ref": "github:c/changed/rev3", "transient": True},
    ]

    def test_none_skips_every_recorded_failure(self):
        self.assertEqual(
            pin.skip_refs(self.FAILURES, pin.Retry.NONE),
            {
                "github:a/permanent/rev1",
                "github:b/transient/rev2",
                "github:c/changed/rev3",
            },
        )

    def test_transient_skips_only_the_permanent_ones(self):
        self.assertEqual(
            pin.skip_refs(self.FAILURES, pin.Retry.TRANSIENT),
            {"github:a/permanent/rev1"},
        )

    def test_all_skips_nothing(self):
        self.assertEqual(pin.skip_refs(self.FAILURES, pin.Retry.ALL), set())

    def test_the_last_row_for_a_ref_is_its_verdict(self):
        # Rows are appended, never rewritten, so a ref that failed
        # permanently and later transiently is transient now.
        self.assertNotIn(
            "github:c/changed/rev3", pin.skip_refs(self.FAILURES, pin.Retry.TRANSIENT)
        )

    def test_a_row_without_a_verdict_is_permanent(self):
        # Rows written before the field existed. Treating them as transient
        # would put every one of them back into the nightly retry.
        rows = [{"ref": "github:d/old/rev4"}]
        self.assertEqual(
            pin.skip_refs(rows, pin.Retry.TRANSIENT), {"github:d/old/rev4"}
        )


if __name__ == "__main__":
    unittest.main()
