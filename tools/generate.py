#!/usr/bin/env python3
"""Generate omniflake's flake.nix from resolved.jsonl.

Two things matter here and both are deliberate.

First, `follows` is emitted into flake.nix rather than rewritten into
flake.lock. A consumer re-locks from our flake.nix, so a lock-level
rewrite (what nix-auto-follow does) is discarded downstream and the
unification is lost. Declaring it here is what lets a consumer redirect
every subflake's nixpkgs with a single `follows` line.

Second, only the inputs in UNIFY are redirected. Following an arbitrary
subflake would pin it to a version its dependents never tested against;
these few are the ones where sharing is routinely safe.
"""
import json, sys

# Foundational inputs that are safe to share across every subflake.
UNIFY = {
    "nixpkgs":      "github:NixOS/nixpkgs/nixos-unstable",
    "flake-utils":  "github:numtide/flake-utils",
    "systems":      "github:nix-systems/default",
    "flake-parts":  "github:hercules-ci/flake-parts",
    "flake-compat": "github:edolstra/flake-compat",
}

# Aliases some flakes use for the same underlying input.
ALIASES = {
    "nixpkgs-unstable": "nixpkgs",
    "nixpkgs_2": "nixpkgs",
    "utils": "flake-utils",
    "flakeUtils": "flake-utils",
    "flake-utils_2": "flake-utils",
}


def main():
    entries = [json.loads(l) for l in sys.stdin if l.strip() and not l.startswith("#")]
    # Deterministic output: sort by attribute name.
    entries.sort(key=lambda e: e["name"])
    names = {e["name"] for e in entries}

    out = ["{"]
    out.append('  description = "omniflake: a very large number of Nix flakes, fetched lazily";')
    out.append("")
    out.append("  inputs = {")

    # Shared foundations first.
    for n, url in UNIFY.items():
        out.append(f'    {n}.url = "{url}";')
    out.append("")

    follows = 0
    for e in entries:
        name = e["name"]
        if name in UNIFY:
            continue
        # Pin an exact rev: no HEAD lookup, so consumers inherit a fixed graph.
        out.append(f'    {name}.url = "github:{e["owner"]}/{e["repo"]}/{e["rev"]}";')
        seen = set()
        for dep in e.get("inputs", []):
            target = ALIASES.get(dep, dep)
            if target not in UNIFY or dep in seen:
                continue
            seen.add(dep)
            out.append(f'    {name}.inputs.{dep}.follows = "{target}";')
            follows += 1
        # A flake that declares no inputs still needs no follows; nothing to do.

    out.append("  };")
    out.append("")
    out.append("  outputs = { self, ... }@inputs: let")
    out.append('    flakes = builtins.removeAttrs inputs [ "self" ];')
    out.append("  in {")
    out.append("    # Every subflake, reachable as omniflake.flakes.<name>.")
    out.append("    inherit flakes;")
    out.append("")
    out.append("    # Metadata that does not force any input to be fetched.")
    out.append("    lib = {")
    out.append("      names = builtins.attrNames flakes;")
    out.append("      count = builtins.length (builtins.attrNames flakes);")
    out.append("    };")
    out.append("  };")
    out.append("}")

    sys.stdout.write("\n".join(out) + "\n")
    print(f"# subflakes={len(entries)} follows={follows}", file=sys.stderr)


if __name__ == "__main__":
    main()
