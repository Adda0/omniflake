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

## `unified`

`omniflake.unified.<name>` substitutes on 12,049 names, where `flakes`
substitutes on five. A graph reaches one `home-manager` and one
`treefmt-nix`, both at the revision the pipeline pinned, rather than the
revision each author happened to lock.

```console
$ nix eval --raw 'github:fzakaria/omniflake#unified.devenv.inputs.nixd.inputs.treefmt-nix.rev'
27b3b12a8e6375f28ebe122f07d230ca5459bbfa
$ nix eval --raw 'github:fzakaria/omniflake#flakes.devenv.inputs.nixd.inputs.treefmt-nix.rev'
db947814a175b7ca6ded66e21383d938df01c227
```

Substitution is a fixed point: the flake substituted in is itself unified, so
the `unified` line above reaches `treefmt-nix` through a `nixd` that had
already been overridden. Nothing is fetched until an attribute is forced, so
an override set naming the whole index costs nothing until one of its names
is matched.

The five foundations still win over the index, which carries entries called
`nixpkgs`, `flake-utils`, `systems`, `flake-parts` and `flake-compat` too.
They have to: `follows` reaches a declared input and nothing else, so taking
those five from the index would cut the one line a consumer uses to unify
omniflake with their own tree.

`unified` is a stronger claim than `flakes`, and it is wrong more often. An
author who locked an older `home-manager` may have done it because the newer
one broke them. Use it when a single graph matters more to you than each
flake working the way its author tested it.

## Which names are substituted

Not every name in the index. An override key is a claim that an input
called that means this flake, and the index cannot make that claim for a
name several repositories share. Twenty-six repositories are named `home`,
one of them holds the bare name, and 49 indexed flakes declare an input
called `home` meaning something else entirely. Substituting on it replaced
every one of them with a stranger's machine configuration.

So a name is an override key when the index knows which repository it
means: one repository claims it, or a [`names.txt`](../names.txt) line
hands it over. `tools/generate.py` writes the result to `unify.json`, which
is committed and readable as `lib.unifyNames`. Today that is 12,049 of the
16,003 index names; `utils`, `home`, `lib`, `system` and `hyprland` are
among the 3,954 left out.

The rule catches names that are contested. It does not catch a name only
one repository claims that people nonetheless use for another project, so
`unified` remains a heuristic and a `names.txt` line remains the way to
correct one.

Matching is still on the exact name. `agenix`'s `darwin` input stays pinned
because the index calls that flake `nix-darwin`.

A name cycle resolves only because evaluation is lazy: `ihp` depends on
`ihp-boilerplate`, which depends on `ihp`. A flake whose `outputs` forced
its way around such a cycle would report infinite recursion for that
attribute rather than for the whole set.

`omniflake.lib.unifyAll { }` is `unified`. Anything passed to it wins over
both the index and the foundations:

```nix
omniflake.lib.unifyAll { home-manager = home-manager; }
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
