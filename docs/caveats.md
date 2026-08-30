# Caveats

**Trust.** Adding omniflake delegates the pinning of every indexed flake to
this repository. Each pin carries a NAR hash, so a fetched tree matches what
was pinned. Whether the pinned revision is a good one is not checked.

**Names are API.** Attribute names do not change once assigned. See
[Adding a flake](./adding-a-flake.md).

**Unification changes inputs.** `omniflake.flakes.<name>` substitutes your
`nixpkgs` and four other inputs into every flake. That is usually what
modules and overlays need, and it is a configuration the flake's author did
not test. `omniflake.pinned.<name>` uses the author's lock instead. See
[Unification](./unification.md).

**Indexed flakes are not flake inputs.** `nix flake metadata` lists five
inputs. `--override-input` cannot reach an indexed flake and
`nix flake update` does not advance one. Use `omniflake.lib.load` or
`omniflake.lib.withOverrides` to substitute inputs.

**Computed locks.** When a flake ships no `flake.lock`, or one that does not
match its `flake.nix`, the index stores the lock Nix computed at pin time.
Inputs written as a branch were resolved when the index was built.

**`pipe-operators`.** Some `flake.nix` files use the pipe operator. They are
pinned with that experimental feature enabled, and evaluating them requires
it as well.

**Checks evaluate a sample.** This repository's checks evaluate a fixed set
of flakes and a random sample, not the whole index.
