"""Tests for the reject ledger resolve.py keeps.

Everything under test is a pure function over dicts and lists, so no test
here issues a GraphQL query or reads a file.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import resolve


class TestOldestRejects(unittest.TestCase):
    """Tests which reject rows a run looks at anyway, over a ledger whose
    rows were checked at different times."""

    LEDGER = {
        ("a", "one"): 100,
        ("b", "two"): 300,
        ("c", "three"): 200,
    }

    def test_the_oldest_rows_come_first(self):
        self.assertEqual(
            resolve.oldest_rejects(self.LEDGER, 2), {("a", "one"), ("c", "three")}
        )

    def test_zero_disables_the_recheck(self):
        # What --refresh-oldest 0 already does for the known set, for a
        # smoke run that should query nothing it does not have to.
        self.assertEqual(resolve.oldest_rejects(self.LEDGER, 0), set())

    def test_asking_for_more_than_there_is_takes_everything(self):
        self.assertEqual(resolve.oldest_rejects(self.LEDGER, 99), set(self.LEDGER))

    def test_ties_break_on_the_repository(self):
        # Two rows seeded in the same second must not make the selection
        # depend on dict order, or a run's query count stops being stable.
        ledger = {("b", "two"): 5, ("a", "one"): 5}
        self.assertEqual(resolve.oldest_rejects(ledger, 1), {("a", "one")})


class TestSelectCandidates(unittest.TestCase):
    """Tests which candidates a run queries, over a pool holding one
    repository of every kind: new, known, merged and rejected."""

    POOL = [
        {"owner": "a", "repo": "new", "stars": 1},
        {"owner": "b", "repo": "known", "stars": 2},
        {"owner": "c", "repo": "merged", "stars": 3},
        {"owner": "d", "repo": "rejected", "stars": 4},
    ]
    KNOWN = {("b", "known"): {}}
    MERGED = {("c", "merged"): {}}
    REJECTS = {("d", "rejected"): 100}

    def select(self, recheck):
        return [
            (c["owner"], c["repo"])
            for c in resolve.select_candidates(
                self.POOL, self.KNOWN, self.MERGED, self.REJECTS, recheck
            )
        ]

    def test_a_rejected_repository_is_skipped(self):
        # The whole point: 8,357 repositories were re-queried every night
        # because nothing recorded that they had been checked.
        self.assertEqual(self.select(recheck=set()), [("a", "new")])

    def test_a_rejected_repository_comes_round_again(self):
        # A repository can add a flake.nix tomorrow, so the record is a
        # timestamp and not a verdict.
        self.assertEqual(
            self.select(recheck={("d", "rejected")}),
            [("a", "new"), ("d", "rejected")],
        )

    def test_known_and_merged_repositories_are_still_skipped(self):
        # Even a re-check does not reach them; success is authoritative.
        self.assertNotIn(("b", "known"), self.select(recheck=set(self.REJECTS)))
        self.assertNotIn(("c", "merged"), self.select(recheck=set(self.REJECTS)))


class TestPruneRejects(unittest.TestCase):
    """Tests that a repository which resolved leaves the ledger, over a
    ledger holding a row for a repository that is in each database."""

    def test_a_resolved_repository_loses_its_row(self):
        # Success is authoritative: a stale reject row for a repository in
        # resolved.jsonl would skip a repository the index already has.
        rejects = {("a", "one"): 1, ("b", "two"): 2, ("c", "three"): 3}
        resolve.prune_rejects(rejects, {("a", "one"): {}}, {("b", "two"): {}})
        self.assertEqual(rejects, {("c", "three"): 3})

    def test_an_unrelated_ledger_is_untouched(self):
        rejects = {("c", "three"): 3}
        resolve.prune_rejects(rejects, {}, {})
        self.assertEqual(rejects, {("c", "three"): 3})


if __name__ == "__main__":
    unittest.main()
