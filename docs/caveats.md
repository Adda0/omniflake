# Caveats

Read these before depending on this.

**Trust.** One input line delegates the pinning of thousands of repositories to
this repository.

**Names are API.** Attribute names cannot be renamed without breaking consumers.
See [Adding a flake](./adding-a-flake.md).

**Unification is a deviation.** Collapsing every subflake onto one nixpkgs is
what you want for closure size and evaluation speed, and it is also not what
each author tested against. Something will occasionally break for that reason.

**Locking here does not mean consumers can lock.** A subflake with a relative
`path:` input resolves it against the root flake, so it points inside
omniflake's own tree. Our lock succeeds and the consumer's fails:

```console
error: Path 'flakes/apple-container/flake.nix' does not exist in
Git repository ".../omniflake"
```

`tools/audit.py` catches these before they ship.

**A megaflake is only as lockable as its worst member.** Flakes in the wild fail
for reasons outside our control — a stale committed `flake.lock` that forces
re-resolution, a registry alias that no longer resolves, a deleted upstream. One
aborts the entire lock, so `tools/lock.sh` quarantines and retries.

**Evaluation used to be quadratic.** Serializing a large lock file was
`O(n²)` in colliding node names, which a megaflake guarantees. Fixed in
[NixOS/nix#16387](https://github.com/NixOS/nix/pull/16387); on 4000 inputs it
took `nix eval` of a constant from 11.49s to 0.54s. Older Nix will be slow here.

**`nix flake check` forces everything.** Consumers are lazy; this repo's CI is
not, which is the point.
