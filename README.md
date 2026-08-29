# omniflake

One flake input that carries a very large number of other flakes, fetched lazily.

```nix
{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.omniflake.url = "github:fzakaria/omniflake";
  inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs";

  outputs = { self, nixpkgs, omniflake, ... }: {
    nixosConfigurations.host = nixpkgs.lib.nixosSystem {
      modules = [
        omniflake.flakes.home-manager.nixosModules.home-manager
        omniflake.flakes.disko.nixosModules.disko
        omniflake.flakes.sops-nix.nixosModules.sops
      ];
    };
  };
}
```

No `inputs.home-manager.url`, no `inputs.disko.url`, no `follows` block per
dependency. One input line, then reach in for what you need.

## Why this works at all

The obvious objection is that this must fetch thousands of repositories. It does
not. Two properties of Nix flakes carry the whole idea:

**Inputs are fetched lazily at evaluation.** An input that no output touches is
never downloaded. You can verify this by corrupting a lock entry — set a `rev` to
all zeros — and evaluating something that does not reference it. It succeeds.
Only forcing that specific input produces a 404.

**Lock inheritance copies metadata, it does not fetch.** When you add omniflake
as an input, your `flake.lock` absorbs its entire transitive node graph without
downloading any of it. Adding a flake with hundreds of inputs locks in well under
a second.

So the download cost is paid once, by this repository's CI, and never by you
unless you actually evaluate a given subflake.

## Why `follows` lives in flake.nix

This is the part that is easy to get wrong, and it is the reason this repository
generates `flake.nix` rather than post-processing `flake.lock`.

A tool like [nix-auto-follow](https://github.com/fzakaria/nix-auto-follow)
rewrites `flake.lock` to collapse duplicate inputs. That is the right thing for a
leaf configuration, where the lock file is the final artifact. It is the wrong
layer for a library, because **a consumer re-locks from your `flake.nix`**. Any
unification that exists only in the lock is regenerated away downstream.

The difference is observable. Given a megaflake with a `fenix` subflake, and a
consumer that sets `inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs"`:

| unification declared in | does the consumer's override reach `fenix`? |
| --- | --- |
| `flake.nix` | yes |
| `flake.lock` (post-processed) | no — `fenix` keeps its own pin |

Declaring `follows` in `flake.nix` is what makes a single line in *your* flake
redirect every subflake onto *your* nixpkgs.

## What gets unified

Only a conservative set of foundational inputs:

```
nixpkgs  flake-utils  systems  flake-parts  flake-compat
```

Following an arbitrary subflake would pin it to a revision its dependents never
tested against. These five are the ones where sharing is routinely safe. Note
that even unifying nixpkgs is a real trade-off: it is what you want for closure
size and evaluation speed, and it is also what will occasionally break a
subflake that depended on something newer or older.

## Caveats

- **Locking here does not mean consumers can lock.** A subflake with a relative
  `path:` input resolves it against the root flake, so it points inside
  omniflake's own tree. Our lock succeeds and the consumer's fails.
  `tools/audit.py` catches these and quarantines them.
- **Trust.** One input line means delegating the pinning of a very large number
  of repositories to this repository.
- **`nix flake check` forces everything.** Consumers are lazy; this repo's own CI
  is not, which is the point.
- **Names are API.** Attribute names are derived from repository names, with the
  owner appended on collision, highest-star-count winning the bare name.
  Renaming one is a breaking change.
- **Staleness.** Pins are exact revisions, refreshed by regenerating.

## How it is built

```
tools/harvest.py    GitHub search, partitioned by topic and star range,
                    to stay under the 1000-result cap per query
tools/resolve.py    one GraphQL round trip per 40 repos, returning HEAD oid,
                    whether flake.nix exists, and flake.lock (whose root node
                    lists each flake's declared input names)
tools/manual.py     adds flakes by hand from manual.txt, including ones
                    that are not on GitHub at all
tools/classify.py   splits off personal machine configurations, which make
                    poor library members and fail locking disproportionately
tools/generate.py   emits flake.nix with pinned revs and follows lines
tools/lock.sh       locks, quarantining members that cannot be locked
tools/audit.py      finds subflakes that lock here but break consumers
tools/deepen.py     derives nested follows from a lock produced by pass 1
tools/update.sh     runs all of the above, in two passes
```

### Adding a flake by hand

Search only finds what people remembered to tag, and it cannot see GitLab or
sourcehut at all. `manual.txt` is committed and read on every run:

```
nix-community/disko          a GitHub repo, pinned to its default branch
github:owner/repo/v1.2.3     pinned to a ref you choose
gitlab:owner/repo            anything else Nix can fetch
```

A bare `owner/repo` becomes a candidate and is pinned by `resolve.py` like any
harvested repo. Anything else is resolved with `nix flake metadata` and pinned
to an exact revision.

### Why two passes

A top-level `follows` only redirects a subflake's *direct* inputs. Most
duplicate foundations sit below that, unreachable from the top. Nix accepts
arbitrary depth:

```nix
agenix.inputs.home-manager.inputs.nixpkgs.follows = "nixpkgs";
```

So pass 1 locks shallowly, purely to produce a lock whose transitive graph can
be read; `deepen.py` walks it and emits a nested `follows` for every path down
to a foundation; pass 2 relocks with those. On a 50-flake tier this took nixpkgs
copies from 54 to 19 and the graph from 726 nodes to 602.

A naive harvest is about 28% personal configurations (616 of 2188 in one run).
They expose nothing worth importing and they are the most likely to break, so
they are filtered into their own tier rather than included.

Regenerate:

```bash
./tools/update.sh              # everything
OMNIFLAKE_TOP=300 ./tools/update.sh   # a smaller tier
```

Locking is the slow step: Nix must fetch every subflake's source to read its
`flake.nix` and discover its inputs. Consumers never pay this.
