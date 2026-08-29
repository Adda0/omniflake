# How it works

## Inputs are lazy

An input no output touches is never fetched. Corrupt a lock entry so it cannot
resolve, and anything that does not reference it still evaluates:

```console
$ sed -i 's/2810303efc.../0000000000000000000000000000000000000000/' flake.lock
$ nix eval .#justB
[ "aarch64-darwin" "aarch64-linux" "x86_64-darwin" "x86_64-linux" ]
```

Only forcing that input fails. This is why thousands of inputs cost nothing.

## Lock inheritance copies pins, it does not fetch

Adding omniflake absorbs its entire transitive node graph into your lock as
metadata. Nothing is downloaded:

```console
$ time nix flake lock
real    0m0.084s
```

The download cost is paid once, here, by CI.

## `follows` is declared in flake.nix, not flake.lock

A consumer re-locks from our `flake.nix`, so any unification that exists only in
our `flake.lock` is regenerated away downstream. A tool like
[nix-auto-follow](https://github.com/fzakaria/nix-auto-follow) is right for a
leaf configuration, where the lock *is* the artifact; it is the wrong layer for
a library.

| unification declared in | consumer's override reaches a grandchild? |
| --- | --- |
| `flake.nix` | yes |
| `flake.lock` | no |

## Nested follows

A top-level `follows` only redirects a subflake's *direct* inputs. Most
duplicate foundations sit below that. Nix accepts an arbitrary chain:

```nix
agenix.inputs.home-manager.inputs.nixpkgs.follows = "nixpkgs";
```

So the build locks once, reads the transitive graph back out of that lock, and
emits a nested `follows` for every path down to a foundation. On a 50-flake tier
this took duplicate nixpkgs nodes from 54 to 19.

Only these are unified:

```
nixpkgs  flake-utils  systems  flake-parts  flake-compat
```

Following an arbitrary subflake would pin it to a revision its dependents never
tested against. So would following `nixpkgs-stable` onto unstable, which is why
matching is on exact input names.
