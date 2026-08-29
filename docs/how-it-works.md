# How it works

## The flakes are not inputs

`flake.nix` declares five inputs: `nixpkgs`, `flake-utils`, `systems`,
`flake-parts` and `flake-compat`. Every other flake is a line in
[`index.json`](../index.json):

```json
"disko": {"locked": {"lastModified": 1781152676, "narHash": "sha256-RxWs…", "owner": "nix-community", "repo": "disko", "rev": "ff8702b4…", "type": "github"}}
```

That is the same `locked` object a `flake.lock` entry carries, and it is used
the same way. When you evaluate `omniflake.flakes.disko`,
[`lib/load.nix`](../lib/load.nix) does what Nix's own
[`call-flake.nix`](https://github.com/NixOS/nix/blob/master/src/libflake/call-flake.nix)
does for a lock file entry: `builtins.fetchTree` on those attributes, read the
flake's `flake.lock`, fetch each input it names, `import` its `flake.nix`, call
`outputs`. Pure evaluation allows it because every node is locked by revision
and NAR hash.

An early version of this repository declared every flake as a real input
instead. That is the design the blog post describes, and it did work, but it
made the consumer inherit every transitive node of every flake — a quarter of
a million lock entries for twelve thousand flakes — and it made Nix fetch all
of those trees serially, aborting on the first one that could not be locked.
The index sidesteps all of it: your lock gains six nodes, and this repository
pins each flake independently.

## Inputs are lazy

An entry no output touches is never fetched. `index.json` is read on every
evaluation, which costs milliseconds; a flake's tree is fetched only when an
attribute of `omniflake.flakes.<name>` is forced.

```console
$ nix eval github:fzakaria/omniflake#lib.count   # reads the index, fetches nothing
$ nix eval github:fzakaria/omniflake#flakes.nh.packages.x86_64-linux.default.name
                                                  # fetches nh, and nothing else
```

## Each flake evaluates from its own lock

A flake that ships a current `flake.lock` is evaluated from it, so its inputs
are exactly the revisions its author tested against. When a flake ships no lock
file, or one Nix considers stale, the lock Nix computes for it is stored under
[`locks/`](../locks) keyed by revision, and `index.json` marks the entry with
`"lock": true`.

Both cases are decided by Nix, not by this repository:
[`tools/pin.py`](../tools/pin.py) runs `nix flake metadata --json` on every
flake, which fetches its tree, resolves its inputs by the usual rules, and
reports the resulting lock. The committed lock is kept when Nix agrees with it
and the computed one is stored otherwise.

## Unification happens at evaluation time

Nix's `follows` redirects an input at lock time. Here the equivalent happens in
the loader: an edge whose input _name_ is in the override set gets the override,
at any depth. `omniflake.flakes.<name>` applies the five foundations;
`omniflake.pinned.<name>` applies nothing. See [Unification](./unification.md).

This is why one `follows` line in your flake reaches
`agenix → home-manager → nixpkgs` without a nested `follows` chain being
generated for it: the redirect is a lookup by name while the graph is walked.
