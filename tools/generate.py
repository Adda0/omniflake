#!/usr/bin/env python3
"""Generate index.json from the library and its pins.

flake.nix is static. What changes between releases is index.json: one line
per flake, mapping its attribute name to the `locked` attributes fetchTree
needs and a flag saying whether a computed lock is stored under locks/.
One entry per line keeps a diff readable when a flake is added, removed or
re-pinned.

A library row without a pin is left out: either tools/pin.py has not seen
its revision yet, or it failed and is in failures.jsonl.

Also prunes what nothing references any more: pins and failures for
revisions no longer in the library, and stored locks no index entry uses.
"""

import argparse, json, os, re, sys

from pin import FOUNDATIONS, flake_ref, lock_key, read_jsonl

# Markers around the status block in README.md.
STATUS_BEGIN = "<!-- BEGIN index-status -->"
STATUS_END = "<!-- END index-status -->"


def load_blocklist(path):
    if not os.path.exists(path):
        return set()
    return {l.strip() for l in open(path) if l.strip() and not l.startswith("#")}


def write_jsonl(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    os.replace(tmp, path)


def write_index(path, index):
    """One entry per line, sorted by name, so diffs stay per-flake."""
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write("{\n")
        names = sorted(index)
        for i, name in enumerate(names):
            entry = json.dumps(index[name], sort_keys=True)
            sep = "," if i + 1 < len(names) else ""
            fh.write(f"  {json.dumps(name)}: {entry}{sep}\n")
        fh.write("}\n")
    os.replace(tmp, path)


def prune_locks(locks_dir, keys_in_use):
    removed = 0
    if not os.path.isdir(locks_dir):
        return removed
    for fname in os.listdir(locks_dir):
        if not fname.endswith(".json"):
            continue
        if fname[: -len(".json")] not in keys_in_use:
            os.remove(os.path.join(locks_dir, fname))
            removed += 1
    return removed


def update_readme(path, stats):
    """Rewrite the status block between the markers, if the file has one."""
    if not os.path.exists(path):
        return
    text = open(path).read()
    pattern = re.compile(re.escape(STATUS_BEGIN) + ".*?" + re.escape(STATUS_END), re.S)
    if not pattern.search(text):
        return
    # The blank line after the opening marker is what prettier wants, and
    # `nix fmt` runs over this file in CI.
    block = "\n".join(
        [
            STATUS_BEGIN,
            "",
            f"- **{stats['indexed']:,} flakes** in the index, from "
            f"**{stats['library']:,} in the library tier** "
            f"({stats['failed']:,} could not be pinned, {stats['unpinned']:,} not yet pinned)",
            f"- {stats['stored_locks']:,} ship no usable lock file and use one computed by Nix",
            f"- One `follows` line in your flake redirects `nixpkgs` in every one of them",
            STATUS_END,
        ]
    )
    open(path, "w").write(pattern.sub(block, text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="library.jsonl")
    ap.add_argument("--pins", default="pins.jsonl")
    ap.add_argument("--failures", default="failures.jsonl")
    ap.add_argument("--locks", default="locks")
    ap.add_argument("--blocklist", default="blocklist.txt")
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--readme", default="README.md")
    args = ap.parse_args()

    blocked = load_blocklist(args.blocklist)
    pins = {p["ref"]: p for p in read_jsonl(args.pins)}
    failures = {f["ref"]: f for f in read_jsonl(args.failures)}

    index = {}
    library_refs = {}
    stats = {"library": 0, "indexed": 0, "failed": 0, "unpinned": 0, "stored_locks": 0}
    for row in read_jsonl(args.library):
        name = row["name"]
        if name in blocked or name in FOUNDATIONS:
            continue
        ref = flake_ref(row)
        library_refs[ref] = name
        stats["library"] += 1

        pin = pins.get(ref)
        if pin is None:
            stats["failed" if ref in failures else "unpinned"] += 1
            continue

        entry = {"locked": pin["locked"]}
        if pin.get("lock"):
            entry["lock"] = True
            stats["stored_locks"] += 1
        index[name] = entry
        stats["indexed"] += 1

    write_index(args.index, index)

    # Keep the databases to what the library still references, and carry
    # the current name on each row so the files read well on their own.
    def current(rows):
        kept = []
        for ref, row in rows.items():
            if ref not in library_refs:
                continue
            kept.append({**row, "name": library_refs[ref]})
        return sorted(kept, key=lambda r: r["name"])

    write_jsonl(args.pins, current(pins))
    write_jsonl(args.failures, current(failures))
    keys_in_use = {lock_key(e["locked"]) for e in index.values() if e.get("lock")}
    stats["pruned_locks"] = prune_locks(args.locks, keys_in_use)

    update_readme(args.readme, stats)
    print("# " + json.dumps(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
