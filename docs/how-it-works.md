# How it works

## The index

`flake.nix` declares five inputs: `nixpkgs`, `flake-utils`, `systems`,
`flake-parts` and `flake-compat`. Every other flake is an entry in
[`index.json`](../index.json), keyed by attribute name:

```json
"disko": {"locked": {"lastModified": 1781152676, "narHash": "sha256-RxWs…", "owner": "nix-community", "repo": "disko", "rev": "ff8702b4…", "type": "github"}}
```

`locked` is the attribute set a `flake.lock` entry carries for that flake:
enough for `builtins.fetchTree` to fetch it in pure evaluation mode.

An entry may also carry `"lock": true`, meaning a lock file for the flake's
inputs is stored under [`locks/`](../locks), named after the revision. See
[Lock files](#lock-files).

## Evaluation

`omniflake.flakes.<name>` is produced by [`lib/load.nix`](../lib/load.nix),
which follows the same steps as Nix's
[`call-flake.nix`](https://github.com/NixOS/nix/blob/master/src/libflake/call-flake.nix):

1. `builtins.fetchTree` on the entry's `locked` attributes.
2. Read the flake's lock file: the stored one if `"lock": true`, otherwise
   the `flake.lock` in the fetched tree, otherwise an empty lock.
3. For each node in that lock, `fetchTree` on its `locked` attributes,
   `import` its `flake.nix`, and call `outputs` with the inputs the lock
   names. Relative `path:` inputs resolve against the parent node's tree.
4. Return the root node's outputs together with the source metadata
   (`outPath`, `rev`, `narHash`, `lastModified`, `sourceInfo`, `inputs`),
   the same shape Nix gives a flake.

Every node is pinned by revision and NAR hash, so pure evaluation permits
the fetches.

Nothing is fetched until an attribute of the result is forced. Reading
`index.json` costs an evaluation of a 3 MB JSON file and no network access.

Fetches nothing:

```console
$ nix eval github:fzakaria/omniflake#lib.count
```

Fetches `nh` and nothing else:

```console
$ nix eval github:fzakaria/omniflake#flakes.nh.packages.x86_64-linux.default.name
```

## Lock files

Each flake is evaluated from its own lock file, so its inputs are the
revisions its author locked.

When a flake ships no `flake.lock`, or one that does not match its
`flake.nix`, the lock Nix computes for it is stored in `locks/<rev>.json`
and the index entry is marked `"lock": true`. The stored lock is the output
of `nix flake metadata --json` for that flake: Nix keeps the entries of the
committed lock that still match `flake.nix` and resolves the rest. See
[Building the index](./building-the-index.md).

## Overrides

`lib/load.nix` takes an `overrides` attribute set. While walking a flake's
lock, any input whose name is in `overrides` receives the override instead
of the node the lock points to, at every depth. `omniflake.flakes.<name>`
passes omniflake's five inputs as overrides; `omniflake.pinned.<name>`
passes none. See [Unification](./unification.md).
