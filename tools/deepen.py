#!/usr/bin/env python3
"""Derive nested `follows` paths from an already-generated flake.lock.

A top-level `follows` only redirects a subflake's *direct* inputs. In a
293-flake build that left 682 nixpkgs nodes, because most duplicates sit
one or more levels below a direct input and are unreachable from the top.

Nix accepts arbitrary depth:

    agenix.inputs.home-manager.inputs.nixpkgs.follows = "nixpkgs";

so the fix is to enumerate every path from each subflake down to an input
named after one of the unified foundations, and emit a follows line for
each. The paths are read out of a lock file we already produced, which
avoids re-fetching every subflake just to learn its input graph.

Reads flake.lock, writes JSON: {subflake: [[path, ...], base]}.
"""
import argparse, json, sys

UNIFY = ["nixpkgs", "flake-utils", "systems", "flake-parts", "flake-compat"]


def paths_for(nodes, start_key, max_depth):
    """Enumerate paths from one subflake to any input named in UNIFY."""
    found = []
    # (node key, path so far, set of keys on this path)
    stack = [(start_key, [], {start_key})]
    while stack:
        key, path, seen = stack.pop()
        if len(path) >= max_depth:
            continue
        for input_name, target in (nodes.get(key, {}).get("inputs") or {}).items():
            # A list means this input already follows something; leave it alone.
            if not isinstance(target, str):
                continue
            new_path = path + [input_name]
            if input_name in UNIFY:
                # Redirect here and stop; the subtree below is replaced anyway.
                found.append((new_path, input_name))
                continue
            if target in seen:
                continue
            stack.append((target, new_path, seen | {target}))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lock", help="a flake.lock produced by a previous pass")
    ap.add_argument("--max-depth", type=int, default=4)
    args = ap.parse_args()

    lock = json.load(open(args.lock))
    nodes = lock["nodes"]
    root_inputs = nodes["root"]["inputs"]

    out = {}
    total = 0
    for subflake, key in root_inputs.items():
        if subflake in UNIFY or not isinstance(key, str):
            continue
        found = paths_for(nodes, key, args.max_depth)
        # A depth-1 path is what generate.py already emits; keep only deeper.
        deep = [(p, b) for p, b in found if len(p) > 1]
        if deep:
            out[subflake] = deep
            total += len(deep)

    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print(f"# subflakes needing deep follows={len(out)} lines={total}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
