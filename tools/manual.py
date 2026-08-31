#!/usr/bin/env python3
"""Add flakes by hand, outside of GitHub search.

Search only finds what people remembered to tag, and it cannot see GitLab,
sourcehut, or a private host at all. manual.txt is the escape hatch and is
committed alongside the database. One entry per line, blank lines and #
comments ignored:

    nix-community/disko          a GitHub repo, pinned to its default branch
    github:owner/repo/v1.2.3     a GitHub repo pinned to a ref you choose
    gitlab:owner/repo            anything else Nix can fetch
    git+https://example.com/x    likewise

A bare owner/repo is emitted as a *candidate*, so resolve.py pins it and
assigns a sticky name like any harvested repo. Everything else cannot go
through the GitHub API, so it is resolved here with `nix flake metadata`
and emitted as a finished database entry.

    --candidates FILE   append bare owner/repo entries here
    --resolved FILE     append fully-resolved entries here
"""

import argparse, json, re, subprocess, sys, time

BARE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def sanitize(name):
    """Flake ref -> a legal Nix attribute name."""
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name.lower())
    if not out or not out[0].isalpha():
        out = "f-" + out
    return out


def resolve_ref(url):
    """Pin an arbitrary flake ref with `nix flake metadata`."""
    try:
        out = subprocess.run(
            ["nix", "flake", "metadata", "--json", url],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if out.returncode != 0:
            print(
                f"# could not resolve {url}: {out.stderr.strip()[:120]}",
                file=sys.stderr,
            )
            return None
        meta = json.loads(out.stdout)
    except Exception as e:
        print(f"# could not resolve {url}: {e}", file=sys.stderr)
        return None

    locked = meta.get("locked", {})
    # The root node of its own lock names the flake's declared inputs.
    inputs = sorted(
        (
            meta.get("locks", {}).get("nodes", {}).get("root", {}).get("inputs", {})
        ).keys()
    )
    name = sanitize(locked.get("repo") or url.rstrip("/").split("/")[-1])

    # Pin to the exact revision. An unpinned url would re-resolve on every
    # consumer lock, defeating the point of shipping a fixed graph.
    rev = locked.get("rev", "")
    kind = locked.get("type", "")
    if kind in ("github", "gitlab", "sourcehut") and locked.get("owner") and rev:
        pinned = f'{kind}:{locked["owner"]}/{locked["repo"]}/{rev}'
    elif locked.get("url") and rev:
        sep = "&" if "?" in locked["url"] else "?"
        pinned = f'{locked["url"]}{sep}rev={rev}'
    else:
        pinned = url

    return {
        "name": name,
        "owner": locked.get("owner", ""),
        "repo": locked.get("repo", name),
        "rev": locked.get("rev", ""),
        # An explicit url wins over the constructed github: ref.
        "url": pinned,
        "inputs": inputs,
        "stars": 0,
        "manual": True,
        # The site's "last checked" date; resolve.py stamps harvested rows
        # the same way. Refreshed on every run, since manual entries are
        # re-resolved each time.
        "resolved_at": int(time.time()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manual", nargs="?", default="manual.txt")
    ap.add_argument("--candidates")
    ap.add_argument("--resolved")
    args = ap.parse_args()

    try:
        lines = open(args.manual).read().splitlines()
    except FileNotFoundError:
        print(f"# no {args.manual}; nothing to add", file=sys.stderr)
        return

    candidates, resolved = [], []
    for line in lines:
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        if BARE.match(entry):
            owner, repo = entry.split("/", 1)
            candidates.append({"owner": owner, "repo": repo, "stars": 0})
            continue
        got = resolve_ref(entry)
        if got:
            resolved.append(got)

    if args.candidates and candidates:
        with open(args.candidates, "a") as fh:
            for c in candidates:
                fh.write(json.dumps(c) + "\n")
    if args.resolved and resolved:
        with open(args.resolved, "a") as fh:
            for r in resolved:
                fh.write(json.dumps(r) + "\n")

    print(
        f"# manual: {len(candidates)} candidate(s), {len(resolved)} resolved",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
