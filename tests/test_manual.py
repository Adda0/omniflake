"""Tests for the star counts manual.py attaches to its entries.

manual.txt names flakes by hand, in more than one spelling and on more
than one forge, so what is under test is which of them GitHub can be asked
about and what happens to the rest. The lookup is injected, so no test
here makes a request.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import manual


class TestGithubRef(unittest.TestCase):
    """Tests which manual entries name a GitHub repository, over one entry
    of every spelling the file accepts."""

    def test_a_bare_entry_is_a_github_repository(self):
        self.assertEqual(
            manual.github_ref("nix-community/disko"), ("nix-community", "disko")
        )

    def test_a_github_reference_is_one_too(self):
        self.assertEqual(manual.github_ref("github:owner/repo"), ("owner", "repo"))

    def test_a_pinned_reference_drops_the_ref(self):
        self.assertEqual(
            manual.github_ref("github:roman/nixDir/v3"), ("roman", "nixDir")
        )

    def test_a_query_string_is_not_part_of_the_repository(self):
        self.assertEqual(
            manual.github_ref("github:owner/repo?dir=sub"), ("owner", "repo")
        )

    def test_another_forge_names_no_github_repository(self):
        # There is a star count on GitLab and sourcehut, and it is not at
        # the endpoint this asks, so these are left alone rather than
        # guessed at.
        self.assertIsNone(manual.github_ref("gitlab:owner/repo"))
        self.assertIsNone(manual.github_ref("git+https://example.com/x"))
        self.assertIsNone(manual.github_ref("sourcehut:~user/repo"))


class TestStarCounts(unittest.TestCase):
    """Tests the map manual.py builds before writing any row, over a list
    holding a GitHub entry, a non-GitHub one and one the lookup fails."""

    ENTRIES = ["hyprwm/Hyprland", "gitlab:owner/repo", "someone/gone"]

    def lookup(self, owner, repo):
        return {("hyprwm", "Hyprland"): 38344}.get((owner, repo))

    def test_a_github_entry_gets_its_count(self):
        counts = manual.star_counts(self.ENTRIES, self.lookup)
        self.assertEqual(counts[("hyprwm", "Hyprland")], 38344)

    def test_an_entry_on_another_forge_is_absent(self):
        counts = manual.star_counts(self.ENTRIES, self.lookup)
        self.assertNotIn(("owner", "repo"), counts)

    def test_a_failed_lookup_is_absent_rather_than_zero(self):
        # Absent and zero mean different things downstream: a row that
        # already records a count keeps it rather than being overwritten
        # with a zero that only means the request failed.
        counts = manual.star_counts(self.ENTRIES, self.lookup)
        self.assertNotIn(("someone", "gone"), counts)

    def test_each_repository_is_asked_about_once(self):
        asked = []

        def counting(owner, repo):
            asked.append((owner, repo))
            return 1

        manual.star_counts(["a/b", "github:a/b", "a/b"], counting)
        self.assertEqual(asked, [("a", "b")])


if __name__ == "__main__":
    unittest.main()
