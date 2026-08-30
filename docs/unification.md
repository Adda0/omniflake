# Unification

`omniflake.flakes.<name>` substitutes five inputs into the flake, matched by
input name, at every depth of its input graph:

```
nixpkgs  flake-utils  systems  flake-parts  flake-compat
```

The substituted values are omniflake's own inputs. With

```nix
inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs";
```

in your flake, every indexed flake's `nixpkgs` is your `nixpkgs`, including
one reached through another flake, such as `agenix` → `home-manager` →
`nixpkgs`.

Matching is on the exact input name. `nixpkgs-stable`, `nixpkgs-unstable`
and similar names are left on the revision in the flake's own lock.

## `pinned`

`omniflake.pinned.<name>` substitutes nothing. Each input is the revision in
the flake's lock file. Use it when a package must be built against the
nixpkgs its author locked.

```console
$ nix run 'github:fzakaria/omniflake#pinned.nh.packages.x86_64-linux.default'
```

## Your own policy

`lib.withOverrides` returns every flake under an override set of your choice;
`lib.load` does the same for one flake.

```nix
let
  mine = omniflake.lib.withOverrides {
    nixpkgs = nixpkgs;
    nixpkgs-stable = nixpkgs-stable;
    nixpkgs-unstable = nixpkgs;
  };
in
mine.sops-nix.nixosModules.sops
```

```nix
omniflake.lib.load "nh" { nixpkgs = nixpkgs-stable; }
```

An override replaces every input of that name wherever it appears in the
graph. When the replaced input is declared with `flake = false`, the
override's source tree (`sourceInfo`) is passed instead of its outputs.

## Scope

Substitution happens during evaluation, in the loader. No lock file is
modified, and a consumer's `nix flake lock` is unaffected. Two consumers with
different override sets evaluate different graphs from the same index.

Each flake still evaluates `import nixpkgs { … }` for itself. Substitution
shares the source revision, not the evaluated package set.
