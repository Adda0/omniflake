#!/usr/bin/env python3
"""Render the notes for a data release cut: what moved into the index.

A cut carries the databases whose bytes changed, which says nothing about
the run that produced them. The index diff is the interesting part and is
otherwise buried in a 12,000-line commit diff nobody opens, so it goes on
the release, which is the only per-run artifact with a stable URL and a
watch notification.

The diff is taken against a git revision, `HEAD` by default. That works
because update.yml cuts the release *before* committing: at cut time the
working tree holds the new index and HEAD still holds the previous one.
A cut taken by hand after the commit has already landed sees no
difference at all, and says so rather than reporting a row of zeroes.

Everything here is a summary of committed facts. Release notes are
mutable and unverified, so nothing reads them back: data-pins.json stays
the manifest.

Usage:
  tools/release-notes.py --files pins.jsonl resolved.jsonl
  tools/release-notes.py --base HEAD~1
"""

import argparse, json, os, subprocess, sys

# The standing sentence, kept at the top of every cut's notes: it is what
# tells a reader the assets are addressed rather than browsed.
MANIFEST_NOTE = (
    "Automated dated cut of the pipeline databases. Addressed by "
    "data-pins.json; assets on this tag are immutable. See "
    "docs/building-the-index.md."
)

# A cut either opens its release or tops up one an earlier cut of the same
# day made. The standing sentence belongs at the top of a release, not
# repeated in a section appended below one that already carries it.
MODE_CUT = "cut"
MODE_TOP_UP = "top-up"

# A --refresh run re-pins thousands of flakes, so the lists are capped.
# New names are the product and get the longer list; a re-pin is only
# interesting for the flakes people have heard of, hence the ranking by
# stars. Removals are always listed in full: they are rare, and they are
# the one change that can break a consumer.
ADDED_SHOWN = 25
REPINNED_SHOWN = 15

# Descriptions come from GitHub and run long; this keeps a row on one line.
DESCRIPTION_CHARS = 80

# The aggregates worth a table, in the order they tell the story: how big
# the index is, how much of it is stored, how fresh it is, what failed,
# and what is still waiting to be pinned.
STATS = [
    ("indexed", "count"),
    ("stored locks", "storedLocks"),
    ("fresh this month", "freshMonth"),
    ("median age (days)", "medianAgeDays"),
    ("hard failures", "failures"),
    ("candidate pool", "candidates"),
    ("stars", "stars"),
]


def git(*args):
    """Run a git command, returning stdout, or None when it fails."""
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def rows(text):
    """Parse jsonl text into a list of rows, ignoring blanks and comments."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(json.loads(line))
    return out


def revision(entry):
    """The identity of a pin: its revision, or the narHash when it has none."""
    return entry["locked"].get("rev") or entry["locked"].get("narHash")


def load(path):
    """A jsonl file keyed by name, or an empty mapping when it is absent."""
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return {r["name"]: r for r in rows(fh.read())}


def format_stat(now, before, key):
    """One table cell pair: today's value, and the change since the base."""
    value = now.get(key)
    if value is None:
        return None
    prior = before.get(key)
    if prior is None:
        return f"{value:,}", "—"
    change = value - prior
    return f"{value:,}", (f"{change:+,}" if change else "—")


def named(name, resolved):
    """One flake as a link to its repository, with its stars when it has any.

    A name missing from resolved.jsonl still renders: the databases are
    fetched at their pin, so a checkout can hold an index newer than them.
    """
    row = resolved.get(name, {})
    owner, repo = row.get("owner"), row.get("repo")
    link = f"[`{name}`](https://github.com/{owner}/{repo})" if owner else f"`{name}`"
    return link + (f" {row['stars']:,}★" if row.get("stars") else "")


def describe(name, resolved):
    """A bullet for a flake nobody has seen before: what it says it is."""
    text = (resolved.get(name, {}).get("description") or "").strip().replace("|", "/")
    if len(text) > DESCRIPTION_CHARS:
        text = text[: DESCRIPTION_CHARS - 1] + "…"
    return f"- {named(name, resolved)}" + (f" — {text}" if text else "")


def by_stars(names, resolved):
    """Names ranked by stars, so a capped list shows what people use."""
    return sorted(names, key=lambda n: (-resolved.get(n, {}).get("stars", 0), n))


def section(title, names, lines, limit):
    """A capped list section, or nothing at all when there is nothing to say."""
    if not names:
        return []
    out = ["", f"### {title} ({len(names):,})", ""]
    out += lines[:limit]
    if len(names) > limit:
        out.append("")
        out.append(f"…and {len(names) - limit:,} more.")
    return out


def summarize(args):
    """The change summary: the counts, the aggregates, and the lists.

    Returns nothing at all when the base index is unreachable, which is
    the normal case outside a checkout and for the very first cut.
    """
    base_index = git("show", f"{args.base}:{args.index}")
    if base_index is None:
        return []

    old = json.loads(base_index)
    new = json.loads(open(args.index).read())

    # A cut taken by hand after the run's commit already landed diffs the
    # index against itself. Reporting that as "0 added" would read as a
    # quiet day rather than as a cut that cannot see its own run.
    if old == new:
        return [
            "",
            f"No change summary: `{args.index}` is identical to `{args.base}`, "
            "so this cut was taken after its index commit had already landed.",
        ]

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    repinned = sorted(
        n for n in set(new) & set(old) if revision(new[n]) != revision(old[n])
    )

    # The base commit, named so a reader can see what the counts are against.
    short = (git("rev-parse", "--short", args.base) or args.base).strip()
    when = (
        git("show", "-s", "--format=%ad", "--date=format:%Y-%m-%d", args.base) or ""
    ).strip()
    since = f"`{short}`" + (f" ({when})" if when else "")
    out = [
        "",
        f"{len(new):,} flakes indexed: {len(added):,} added, {len(removed):,} "
        f"removed, {len(repinned):,} re-pinned since {since}.",
    ]

    # The aggregates, from the row history.py wrote for this run against the
    # row that was committed at the base.
    history = rows(open(args.history).read()) if os.path.exists(args.history) else []
    base_history = rows(git("show", f"{args.base}:{args.history}"))
    now = history[-1] if history else {}
    before = base_history[-1] if base_history else {}
    cells = [(label, format_stat(now, before, key)) for label, key in STATS]
    cells = [(label, cell) for label, cell in cells if cell]
    if cells:
        out += ["", "| | now | change |", "| --- | --- | --- |"]
        out += [f"| {label} | {value} | {change} |" for label, (value, change) in cells]

    # The names themselves. resolved.jsonl is this run's, so a flake added
    # today already has its stars and description here.
    resolved = load(args.resolved)
    out += section(
        "Added",
        added,
        [describe(n, resolved) for n in by_stars(added, resolved)],
        ADDED_SHOWN,
    )
    out += section("Removed", removed, [f"- `{n}`" for n in removed], len(removed))
    out += section(
        "Re-pinned",
        repinned,
        [
            f"- {named(n, resolved)} `{revision(old[n])[:8]}` → `{revision(new[n])[:8]}`"
            for n in by_stars(repinned, resolved)
        ],
        REPINNED_SHOWN,
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="the checkout to read and diff in")
    ap.add_argument("--base", default="HEAD", help="revision to diff against")
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--history", default="history.jsonl")
    ap.add_argument("--resolved", default="resolved.jsonl")
    ap.add_argument(
        "--mode",
        choices=[MODE_CUT, MODE_TOP_UP],
        default=MODE_CUT,
        help="whether these notes open a release or are appended to one",
    )
    ap.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="the database files this cut carries, for the header line",
    )
    args = ap.parse_args()

    # Every path and every git command below is relative to the checkout,
    # which is the caller's directory rather than this script's: under
    # `nix run` this file is a store copy.
    os.chdir(args.root)

    carried = ", ".join(
        f"`{c}`" for c in sorted(os.path.basename(f) for f in args.files)
    )
    if args.mode == MODE_TOP_UP:
        out = [f"Topped up with {carried}." if carried else "Topped up."]
    else:
        out = [MANIFEST_NOTE]
        if carried:
            out += ["", f"Carries {carried}."]

    # The cut is the pipeline's durability step and the notes are prose on
    # top of it, so a summary that cannot be rendered costs a paragraph,
    # never the release.
    try:
        out += summarize(args)
    except Exception as err:
        print(f"release-notes: no change summary: {err}", file=sys.stderr)
        out += ["", "No change summary: the index diff could not be rendered."]

    print("\n".join(out))


if __name__ == "__main__":
    main()
