# Unification

Across a few dozen well-known flakes there are typically as many distinct
`nixpkgs` revisions. For a NixOS module or an overlay that is wrong as well as
wasteful: a module has to evaluate against the nixpkgs of the system it is
imported into, or options and packages drift apart.

So `omniflake.flakes.<name>` substitutes five inputs, by exact name, at every
depth of the flake's input graph:

```
nixpkgs  flake-utils  systems  flake-parts  flake-compat
```

`nixpkgs` is whatever you gave omniflake, which with

```nix
inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs";
```

is your own. Exact names only: `nixpkgs-stable`, `nixpkgs-unstable`,
`nixpkgs-master` are left on the pins their authors chose. Following those onto
your nixpkgs is not risky, it is wrong, and it is one line away if you want it
anyway.

## Packages may prefer the author's pins

A package built against a nixpkgs its author never tried can fail where the
author's pin builds. For that case every flake is also reachable as its author
locked it:

```console
$ nix run 'github:fzakaria/omniflake#pinned.nh.packages.x86_64-linux.default'
```

`pinned` substitutes nothing. The flake's `nixpkgs` is the revision in its own
lock file, fetched on demand like everything else.

## Your own policy

Both attributes are the same loader with a different override set, and the set
is yours to choose:

```nix
let
  mine = omniflake.lib.withOverrides {
    nixpkgs = nixpkgs;
    nixpkgs-stable = nixpkgs-stable;   # you decide these are the same thing
    nixpkgs-unstable = nixpkgs;
  };
in
mine.sops-nix.nixosModules.sops
```

or for a single flake:

```nix
omniflake.lib.load "nh" { nixpkgs = nixpkgs-stable; }
```

An override replaces every input of that name wherever it appears. A
`flake = false` input (the usual way `flake-compat` is declared) receives the
override's source tree rather than its outputs, which is what `import` of it
expects.

## What this is not

It is not the `follows` mechanism. Nothing is rewritten in any lock file; the
substitution happens while the graph is walked at evaluation time, and only for
the evaluation that asked for it. Two consumers with different policies see
different graphs from the same index, and `nix flake lock` in either is
unaffected.

It also does not deduplicate _evaluation_ of nixpkgs. Each subflake still calls
`import nixpkgs { … }` for itself, exactly as it would under `follows`.
