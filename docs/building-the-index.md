# Building the index

```console
# discover new flakes, pin them, regenerate
$ ./tools/update.sh

# also re-pin every known flake
$ ./tools/update.sh --refresh

# skip GitHub search; pin and regenerate
$ ./tools/update.sh --no-harvest
```

`PIN_JOBS` sets how many `nix flake metadata` processes run at once (default
16). The same steps are available as apps: `nix run .#update`,
`nix run .#pin`, `nix run .#generate`.

## Refresh

Each run re-resolves the known repositories that were resolved longest ago,
`REFRESH_OLDEST` of them (default 2,000), in addition to any new ones. A
repository whose default branch moved gets a new revision and is pinned
again; one that did not costs nothing beyond the lookup. With about 16,000
repositories and a daily run, every flake is refreshed about every eight
days. `--refresh` re-resolves all of them in one run.

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
regenerated, so names stay stable.

It is written sorted by attribute name, with each row's keys sorted too, so
a run's diff is the rows whose facts changed and nothing else. Processing
order is unchanged — the highest-starred candidate still wins a new name —
but a rolling refresh no longer moves the rows it touches to the end of the
file and shifts every row after them.

`pins.jsonl` holds one row per pinned flake reference: the `locked`
attributes and whether a computed lock was stored. A revision never changes,
so a pinned reference is not fetched again.

`failures.jsonl` holds the references Nix could not lock, with the error.
They are skipped until `tools/pin.py --retry-failed`.

`locks/<rev>.json` holds Nix's computed lock for a flake whose committed
`flake.lock` is absent or does not match its `flake.nix`.

`index.json` is generated from the files above and is what `flake.nix`
reads.

## Pinning

Pinning a flake means running `nix flake metadata --json` on its exact
reference. Nix fetches the tree and returns its `locked` attributes,
including the NAR hash, and `locks`, the lock file it computes for the
flake's inputs. When `locks` equals the committed `flake.lock`, nothing else
is stored. Otherwise `locks` is written to `locks/<rev>.json`.

Each new revision costs one download. A routine run pins only revisions that
changed since the last one.

`pin.py` runs without a GitHub token, which keeps tarball downloads outside
the API quota, then `update.sh` runs a second pass over the failures with a
token (`--retry-failed --use-token`), for flakes that need the API to
resolve a branch name. `--use-token` uses Nix's configured `access-tokens`
or `GH_TOKEN`.

`pin.py` also repacks Nix's tarball cache every 500 pins (`--repack-every`),
which keeps fetches fast over a long run.

## Continuous integration

`update.yml` runs the pipeline daily and commits the regenerated index to
`main`. `check.yml` runs on pushes and pull requests: it locks the
flake, regenerates the index and fails on any difference, runs
`nix flake check`, and evaluates a random sample of flakes for the job
summary. `pages.yml` builds and deploys the site.
