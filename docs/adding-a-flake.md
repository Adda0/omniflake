# Adding or removing a flake

## Adding

Search only finds what people remembered to tag, and it cannot see GitLab or
sourcehut at all. `manual.txt` is committed and read on every run:

```
nix-community/disko          a GitHub repo, pinned to its default branch
github:owner/repo/v1.2.3     pinned to a ref you choose
gitlab:owner/repo            anything else Nix can fetch
```

A bare `owner/repo` becomes a candidate and is resolved by `tools/resolve.py`
like any harvested repo. Anything else is resolved with `nix flake metadata`
and pinned to an exact revision.

Open a pull request adding a line, then regenerate:

```console
$ ./tools/update.sh --no-harvest
```

This pins only what is new: the flake's tree is fetched once by
`nix flake metadata`, its `locked` attributes land in `pins.jsonl`, and
`index.json` gains a line. Commit `manual.txt`, `resolved.jsonl`, `pins.jsonl`,
`index.json` and anything new under `locks/`.

The `check` workflow regenerates the index on every pull request and fails if
the committed one differs, so a hand edit to `index.json` cannot drift from the
databases.

## Removing

Add the attribute name to `blocklist.txt`:

```
# deliberate removals, one attribute name per line
some-flake
```

and regenerate. The row stays in `resolved.jsonl`, so the name stays reserved
(see below); it just stops being indexed. Flakes that merely fail to pin do not
need an entry: `tools/pin.py` records them in `failures.jsonl` with the reason.

## Names are API

An attribute name is derived from the repository name, with the owner appended
on collision, and **never changes once assigned**. A repo that later gains
stars cannot take a bare name from the repo that holds it, because every
consumer writing `omniflake.flakes.<name>` would silently get a different
flake.

Names were assigned once, by stars, before the first index was published. That
was the last time a name moved.
