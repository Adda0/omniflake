# Building the index

```console
# discover new flakes, pin them, regenerate
$ ./tools/update.sh

# also re-pin every known flake
$ ./tools/update.sh --refresh

# skip GitHub search; pin and regenerate
$ ./tools/update.sh --no-harvest
```

`PIN_JOBS=64` sets how many `nix flake metadata` processes run at once. The
same steps are available as apps: `nix run .#update`,
`nix run .#pin -- --jobs 64`, `nix run .#generate`.

## Tools

| tool          | function                                                                                                             |
| ------------- | -------------------------------------------------------------------------------------------------------------------- |
| `harvest.py`  | GitHub search by `language:Nix` and topic, partitioned by star range and push date to stay under the 1000-result cap |
| `manual.py`   | reads `manual.txt`, including flakes outside GitHub                                                                  |
| `resolve.py`  | one GraphQL query per 40 repositories: HEAD commit and whether `flake.nix` exists                                    |
| `describe.py` | fills in a repository description per row, for the site's search                                                     |
| `classify.py` | separates personal machine configurations from the library tier                                                      |
| `pin.py`      | runs `nix flake metadata --json` per flake in parallel; records `locked` and, where needed, Nix's computed lock      |
| `generate.py` | writes `index.json`, prunes unused pins and locks, updates the README status block                                   |

## Data files

`resolved.jsonl` is the database of known repositories: name, owner, repo,
revision, stars, description. It is committed and extended on each run, not
regenerated, so names stay stable and repositories are not re-resolved.

`pins.jsonl` holds one row per pinned flake reference: the `locked`
attributes and whether a computed lock was stored. A revision never changes,
so a pinned reference is not fetched again.

`failures.jsonl` holds the references Nix could not lock, with the error.
They are skipped until `tools/pin.py --retry-failed`.

`locks/<rev>.json` holds Nix's computed lock for a flake whose committed
`flake.lock` is absent or does not match its `flake.nix`. Files are named by
revision, so a rename does not affect them and two repositories at the same
commit share one file.

`index.json` is generated from the files above and is what `flake.nix`
reads.

## Pinning

Pinning a flake means running `nix flake metadata --json` on its exact
reference. Nix fetches the tree and returns its `locked` attributes,
including the NAR hash, and `locks`, the lock file it computes for the
flake's inputs. When `locks` equals the committed `flake.lock`, nothing else
is stored. Otherwise `locks` is written to `locks/<rev>.json`.

Each new revision costs one download and a NAR hash computation. The initial
index of 12,000 flakes took a few hours on a 256-core machine at 64
processes. A weekly run pins only revisions that changed.

### Tarball cache

Nix unpacks each fetched tarball into a git repository at
`~/.cache/nix/tarball-cache-v2` and writes one packfile per tarball. It does
not repack. Object lookups consult every packfile, so fetch time grows with
the number of packfiles. In the initial run the rate fell from 190 pins per
minute to 3 per minute at 60,000 packfiles.

`pin.py` runs `git repack --geometric=2 -d` on the cache every 500 pins
(`--repack-every`; 0 disables). `git repack -a -d` must not be used on this
repository: it has no refs, so git treats every object as unreachable and
deletes all packfiles.

### GitHub quotas

With a token in Nix's `access-tokens`, tarballs are downloaded from
`api.github.com`, which is limited to 5,000 requests per hour. Without a
token, tarballs come from the archive endpoint, which has no such limit.

Resolving a branch name to a revision requires an API call regardless, and
that call is limited to 60 per hour without a token. A flake needs it when
its lock is stale and an input is written as a branch.

`pin.py` unsets the token by default. Failures caused by the API limit are
retried with the token in a second pass; `update.sh` runs both:

```console
# first pass, without a token
$ ./tools/pin.py --jobs 64

# second pass over the failures, with a token
$ ./tools/pin.py --jobs 16 --retry-failed --use-token
```

`--use-token` uses Nix's configured tokens, or `GH_TOKEN` from the
environment.

## Continuous integration

`update.yml` runs the pipeline weekly and opens a pull request with the
regenerated index. `check.yml` runs on pushes and pull requests: it locks the
flake, regenerates the index and fails on any difference, then evaluates a
fixed set of flakes and a random sample, through both `flakes` and `pinned`.
`pages.yml` builds and deploys the site.
