"""Tests for the attribute name resolve.py gives a repository.

Everything under test is a pure function over dicts and counters, so no
test here issues a GraphQL query. load_reserved is the one exception and
reads a file, so it gets a temporary one.
"""

import collections
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import resolve


class TestLoadReserved(unittest.TestCase):
    """Tests that names.txt parses, over a file holding a comment, a blank
    line, an inline comment and mixed case."""

    FILE = """\
# a comment
nix-community/home-manager   home-manager

NixOS/nixpkgs                nixpkgs   # an inline comment
"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        self.tmp.write(self.FILE)
        self.tmp.close()
        self.addCleanup(os.unlink, self.tmp.name)

    def test_entries_are_read_and_keyed_lowercased(self):
        # The key is lowercased because GitHub is case-insensitive about
        # owners and repositories and the file is written by hand.
        self.assertEqual(
            resolve.load_reserved(self.tmp.name),
            {
                ("nix-community", "home-manager"): "home-manager",
                ("nixos", "nixpkgs"): "nixpkgs",
            },
        )

    def test_a_missing_file_reserves_nothing(self):
        self.assertEqual(resolve.load_reserved("/nonexistent/names.txt"), {})


class TestChooseName(unittest.TestCase):
    """Tests which name a repository gets, over the four cases that decide
    it: a hand-assigned name, a name the repository already holds, a
    repository name only one repository claims, and one several claim."""

    RESERVED = {("nixified-ai", "flake"): "nixified-ai"}

    def choose(self, owner, repo, prior=None, claims=None, taken=None, used=None):
        return resolve.choose_name(
            owner,
            repo,
            prior,
            self.RESERVED,
            collections.Counter(claims or {}),
            taken or {},
            collections.Counter(used or {}),
        )

    def test_a_hand_assigned_name_wins_over_the_derived_one(self):
        self.assertEqual(self.choose("nixified-ai", "flake"), "nixified-ai")

    def test_a_hand_assigned_name_wins_over_the_name_already_held(self):
        # The migration case: names.txt is how a name that was already
        # assigned gets corrected, so it has to beat stickiness.
        prior = {"name": "flake"}
        self.assertEqual(
            self.choose("nixified-ai", "flake", prior=prior), "nixified-ai"
        )

    def test_a_repository_keeps_the_name_it_was_given(self):
        prior = {"name": "disko"}
        self.assertEqual(self.choose("nix-community", "disko", prior=prior), "disko")

    def test_a_name_only_one_repository_claims_is_taken_bare(self):
        self.assertEqual(
            self.choose("nix-community", "disko", claims={"disko": 1}), "disko"
        )

    def test_a_name_several_repositories_claim_is_qualified(self):
        # 110 repositories are named "flake" and 61 "home-manager". A bare
        # name that several repositories could equally mean identifies
        # none of them, so nobody gets it without a names.txt line.
        self.assertEqual(
            self.choose("someone", "home-manager", claims={"home-manager": 61}),
            "home-manager-someone",
        )

    def test_a_name_another_repository_holds_is_not_taken(self):
        taken = {"disko": ("nix-community", "disko")}
        self.assertEqual(
            self.choose("fork", "disko", claims={"disko": 1}, taken=taken),
            "disko-fork",
        )

    def test_two_repositories_in_one_run_do_not_both_take_the_name(self):
        self.assertEqual(
            self.choose("second", "nh", claims={"nh": 1}, used={"nh": 1}), "nh-second"
        )


class TestApplyReserved(unittest.TestCase):
    """Tests that a hand-assigned name is freed, over a database where the
    name it asks for is held by a different repository."""

    def test_the_incumbent_is_displaced_to_its_qualified_name(self):
        known = {
            ("someone", "nixvim"): {
                "name": "nixvim",
                "owner": "someone",
                "repo": "nixvim",
            },
        }
        moved = resolve.apply_reserved(known, {("nix-community", "nixvim"): "nixvim"})
        self.assertEqual(known[("someone", "nixvim")]["name"], "nixvim-someone")
        self.assertEqual(moved, 1)

    def test_the_repository_the_name_belongs_to_is_left_alone(self):
        known = {
            ("nix-community", "nixvim"): {
                "name": "nixvim",
                "owner": "nix-community",
                "repo": "nixvim",
            },
        }
        moved = resolve.apply_reserved(known, {("nix-community", "nixvim"): "nixvim"})
        self.assertEqual(known[("nix-community", "nixvim")]["name"], "nixvim")
        self.assertEqual(moved, 0)


if __name__ == "__main__":
    unittest.main()
