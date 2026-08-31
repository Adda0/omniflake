# Adding or removing a flake

## Adding

`manual.txt` lists flakes that GitHub search does not find, including flakes
outside GitHub. It is read on every run. One entry per line:

```
nix-community/disko
github:owner/repo/v1.2.3
gitlab:owner/repo
```

- `owner/repo`: a GitHub repository, pinned to its default branch. It
  becomes a candidate and is resolved by `tools/resolve.py` like a harvested
  repository.
- Any other flake reference Nix can fetch, including a specific ref. It is
  resolved with `nix flake metadata` and pinned to an exact revision.

To add a flake, add a line to `manual.txt` and regenerate:

```console
$ ./tools/update.sh --no-harvest
```

The new flake is fetched once by `nix flake metadata`, its `locked`
attributes are written to `pins.jsonl`, and `index.json` gains an entry.

`resolved.jsonl` and `pins.jsonl` are not committed. Cut a release for the
bytes they now hold, which repoints `data-pins.json`:

```console
$ ./tools/cut-data-release.sh
```

Then commit `manual.txt`, `data-pins.json`, `index.json` and any new file
under `locks/`.

The `check` workflow regenerates the index on every pull request and fails
if the committed `index.json` differs from the generated one. It also
re-derives every pin the pull request adds or changes with `nix flake
metadata` and evaluates every new name, so the committed `locked`
attributes are checked against what the source really serves. The same
check runs locally with `nix run .#verify`.

## Removing

Add the attribute name to `blocklist.txt`, one per line, and regenerate:

```
some-flake
```

The row stays in `resolved.jsonl`, so the name stays reserved; the flake is
no longer indexed. Flakes that fail to pin do not need an entry: `tools/pin.py`
records them in `failures.jsonl` with the error.

## Names

An attribute name is derived from the repository name. When two repositories
have the same name, the one with more stars gets the bare name and the others
get the owner appended: `home-manager` and `home-manager-rc-14`.

A name never changes once assigned. A repository that later gains stars does
not take a bare name from the repository holding it, because consumers refer
to flakes by name.
