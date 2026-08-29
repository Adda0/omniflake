# Building the index

```console
$ ./tools/update.sh              # discover new flakes, pin them, regenerate
$ ./tools/update.sh --refresh    # also re-pin everything already known
$ ./tools/update.sh --no-harvest # skip GitHub search; pin and regenerate
```

`PIN_JOBS=64` sets how many `nix flake metadata` processes run at once. The
same steps are reachable without a checkout of the tools:
`nix run .#update`, `nix run .#pin -- --jobs 64`, `nix run .#generate`.

| tool          | what it does                                                                                                                        |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `harvest.py`  | GitHub search by `language:Nix` and topic, partitioned by star range and push date to stay under the 1000-result cap                |
| `manual.py`   | flakes listed by hand in `manual.txt`, including non-GitHub ones                                                                    |
| `resolve.py`  | one GraphQL round trip per 40 repos: HEAD commit and whether `flake.nix` exists                                                     |
| `classify.py` | splits off personal machine configurations                                                                                          |
| `pin.py`      | `nix flake metadata --json` per flake, in parallel: the `locked` attributes, and Nix's computed lock where the committed one is off |
| `generate.py` | emits `index.json`, prunes stale pins and locks, refreshes the README status block                                                  |

## Databases

`resolved.jsonl` is committed and added to, not regenerated. Rediscovering
everything on each run wastes hundreds of API calls and risks reassigning
names.

`pins.jsonl` is keyed by exact flake reference. A revision never changes, so a
pin is never recomputed; a routine run costs only what is new. `failures.jsonl`
records refs Nix could not lock, with the error, and they are not retried
until `tools/pin.py --retry-failed`.

`locks/<rev>.json` holds Nix's computed lock for a flake whose committed
`flake.lock` is absent or stale. It is keyed by revision so a rename cannot
orphan it and two forks at the same commit share one file.

## Pinning is the slow step, once

The narHash of a tree cannot be known without downloading it, so every new
revision costs one fetch. Twelve thousand flakes took a few hours on a large
machine at 96 processes, dominated by Nix importing each tarball into its Git
cache and hashing it. After that, a weekly run touches a few hundred revisions.

### Nix's tarball cache needs repacking

Nix unpacks every fetched tarball into a git-backed cache
(`~/.cache/nix/tarball-cache-v2`) and writes one packfile per tarball, never
repacking. libgit2 consults every pack index on every object lookup, so each
fetch gets slower with every tarball ever fetched. The first run measured 190
pins per minute at the start and 3 per minute once 60,000 packs had
accumulated, with each Nix process holding 4,000 of them open.

`pin.py` folds the cache into a geometric progression of packs every 500 pins
(`--repack-every`; 0 disables). Not `git repack -a -d`: the cache has no refs,
so to git every object is unreachable, and that command packs nothing and then
deletes everything. `git repack --geometric=2 -d` works from the list of packs
instead; 19,655 packs folded into one in 45 seconds.

### GitHub's API quota

Run without a GitHub token in Nix's `access-tokens`: with one, Nix downloads
from `api.github.com`, which is subject to the 5,000 requests per hour quota.
Without one it uses the archive endpoint, which is not. `pin.py` unsets it by
default (`--use-token` keeps it).

## Continuous integration

`update.yml` runs the whole pipeline weekly and opens a pull request with the
new `index.json`. `check.yml` runs on every push and pull request: it locks the
flake, regenerates the index and fails on drift, then evaluates a handful of
well-known flakes and a random slice of the index, both unified and pinned.
