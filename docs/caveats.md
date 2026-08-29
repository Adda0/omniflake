# Caveats

Read these before depending on this.

**Trust.** One input line delegates the pinning of thousands of repositories
to this repository. Every pin carries a NAR hash, so what you fetch is what was
pinned; whether what was pinned is any good is a different question.

**Names are API.** Attribute names cannot be renamed without breaking
consumers. See [Adding a flake](./adding-a-flake.md).

**Unification is a deviation.** Substituting your `nixpkgs` into every flake is
what you want for modules and overlays, and it is also not what each author
tested against. `omniflake.pinned.<name>` is there for when that matters. See
[Unification](./unification.md).

**These are not flake inputs.** `nix flake metadata` lists five inputs, not
thousands. `--override-input omniflake/foo` cannot reach a subflake, and
`nix flake update` does not advance one; this repository's update job does. To
substitute something into a flake, use `omniflake.lib.load` or
`omniflake.lib.withOverrides`.

**A stale lock is repaired by Nix, at index time.** When a flake ships no
`flake.lock`, or one that no longer matches its `flake.nix`, the lock Nix
computes for it is stored here. Inputs that lock resolved from a moving branch
were resolved when the index was built, not when the author last did.

**Some flakes need `pipe-operators`.** A `flake.nix` written with the pipe
operator cannot be parsed without that experimental feature. Such flakes are
pinned with it enabled, and evaluating one needs it enabled too.

**`nix flake check` here forces everything.** Consumers are lazy; this
repository's checks evaluate a sample, and its formatter is one of its own
flakes.
