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

## Harvest

GitHub returns at most 1,000 results for a search, however many match, and
there is no cursor past it. `harvest.py` therefore issues each query as a
set of disjoint slices small enough to read to the end, and takes the
union.

Star ranges are the first axis, since every repository has exactly one
star count. A bucket still over the cap is bisected on creation date until
each piece fits. The count comes from the API — `total_count` reports the
true size of a match even though the results are capped — so the partition
follows the data rather than a fixed list of windows. A hand-tuned
boundary looks correct until the bucket behind it crosses 1,000, and then
drops repositories silently; that is how a 3-star and a 5-star flake were
absent from the index while sitting in a bucket the search claimed to
cover.

The split is on creation date rather than push date because a creation
date never moves. The same partition comes out of every run, and no
repository slips between two windows by being pushed to in between.

One bucket is deliberately not enumerated. `language:Nix stars:0` alone
holds about 65,000 repositories, nearly all of them abandoned personal
configurations, and reading it in full would put some 55,000 rows through
`resolve.py`, `describe.py` and `pin.py` to find a handful of libraries.
It is sampled through fixed push-date windows instead, so what comes back
is what has been touched most recently. A flake that anyone has starred at
all leaves that bucket for the enumerated path.

## Refresh

Each run re-resolves the known repositories that were resolved longest ago,
`REFRESH_OLDEST` of them (default 2,000), in addition to any new ones. A
repository whose default branch moved gets a new revision and is pinned
again; one that did not costs nothing beyond the lookup. With about 16,000
repositories and a daily run, every flake is refreshed about every eight
days. `--refresh` re-resolves all of them in one run.

## Tools

| tool                  | function                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `harvest.py`          | GitHub search by `language:Nix` and topic, partitioned by star range and creation date to stay under the 1000-result cap |
| `manual.py`           | reads `manual.txt`, including flakes outside GitHub                                                                      |
| `resolve.py`          | one GraphQL query per 40 repositories: HEAD commit and whether `flake.nix` exists                                        |
| `describe.py`         | fills in a repository description per row, for the site's search                                                         |
| `classify.py`         | separates personal machine configurations from the library tier                                                          |
| `pin.py`              | runs `nix flake metadata --json` per flake in parallel; records `locked` and, where needed, Nix's computed lock          |
| `generate.py`         | writes `index.json`, prunes unused pins and locks, updates the README status block                                       |
| `history.py`          | appends one aggregate row a day to `history.jsonl`; `--from-git` recovers past days from index.json's history            |
| `fetch-data.sh`       | downloads the databases `data-pins.json` pins, or `--check`s the ones already present                                    |
| `release-notes.py`    | renders a cut's notes: what the run added, removed and re-pinned, against `HEAD`                                         |
| `cut-data-release.sh` | uploads the databases whose bytes moved to a dated release and repoints the pins                                         |
| `bump-data-pin.sh`    | records `{tag, narHash}` per file in `data-pins.json`                                                                    |

## Data files

Three of these are committed and three are not. `index.json`, `locks/` and
`failures.jsonl` are in the flake tree because evaluation reads the first
two and the third is small. `resolved.jsonl`, `pins.jsonl` and
`candidates.jsonl` are pipeline state that nothing evaluates: they were
10.7 MB of the 20 MB a consumer unpacked, so they live on dated GitHub
releases instead, addressed by `data-pins.json`.

A release asset is a mutable pointer — a tag and a name, re-uploadable at
will. `data-pins.json` records a `narHash` per file, so the committed
manifest is what makes the pair immutable: a swapped asset fails the hash
and the build stops. `tools/fetch-data.sh` puts the files in a checkout,
and `nix/data.nix` fetches them for the site build as fixed-output
derivations, which keeps `nix flake show` and `nix flake check` offline.

A run that changes any of the three needs a cut before its commit:

```console
$ ./tools/cut-data-release.sh          # tag data-<today, UTC>
```

The notes on a cut carry the run's index diff: how many flakes were added,
removed and re-pinned, today's aggregate row against the one committed at
`HEAD`, and the names themselves — every removal, and the highest-starred
additions and re-pins, capped so a `--refresh` run does not paste twelve
thousand lines. `tools/release-notes.py` renders them, and it is prose over
committed facts: nothing reads it back, `data-pins.json` is still the
manifest.

It works by diffing the working tree against `HEAD`, which is the previous
index only because the cut happens before the commit. Run by hand after that
commit has landed, it has nothing to compare and says so rather than
reporting a row of zeroes. A tag that is being topped up keeps the notes of
its first cut and has the new section appended, since `gh release create`
never runs a second time for it.

`resolved.jsonl` is the database of known repositories: name, owner, repo,
revision, stars, description. It is kept and extended on each run, not
regenerated, so names stay stable.

It is written sorted by attribute name, with each row's keys sorted too, so
a run's diff is the rows whose facts changed and nothing else. Processing
order is unchanged — the highest-starred candidate still wins a new name —
but a rolling refresh no longer moves the rows it touches to the end of the
file and shifts every row after them.

`pins.jsonl` holds one row per pinned flake reference: the `locked`
attributes, whether a computed lock was stored, the size of the lock's graph
and a summary of it. A revision never changes, so a pinned reference is not
fetched again.

The summary is `lock_types`, a count of the fetcher each node of the lock
uses, and `lock_nixpkgs`, the revision and date of the first `NixOS/nixpkgs`
node. Both are one pass over a lock `pin.py` already holds, and they are
what lets the site say what the index's input graph is made of without
re-fetching twelve thousand trees. `--summarize` fills them in for rows
pinned before the field existed: it reads the stored lock where there is
one and fetches the committed `flake.lock` at the pinned revision where
there is not, which is the same lock the loader uses whenever `lock` is
false.

`failures.jsonl` holds the references Nix could not lock, with the error.
They are skipped until `tools/pin.py --retry-failed`.

`locks/<rev>.json` holds Nix's computed lock for a flake whose committed
`flake.lock` is absent or does not match its `flake.nix`.

`index.json` is generated from the files above and is what `flake.nix`
reads.

A flake whose current revision has no pin is held at the last revision that
did, rather than dropped. An attribute name is API, and the usual reason a
pin is missing is that GitHub rate-limited the run that tried to make it —
`resolve.py` keeps the row on failure for the same reason, and without this
the two together would still lose the flake: resolve advances the revision,
pin fails on it, and the entry disappears along with the older pin and lock
that pruning then collects. The README status block counts anything being
held. A flake leaves the index only by leaving the library: blocklisted,
reclassified as personal, or gone from `resolve.py`.

`history.jsonl` is one aggregate row per day: how many flakes are indexed,
how many use a computed lock, the size of the graph the index holds, the
median age, the tier counts. It is committed, because at 270 bytes a row it
costs 87 KiB a year and appends rather than rewrites, and because the trends
the site draws should be auditable in the same diff as the index they
describe. `history.py` records it at the end of a run, while `library.jsonl`
and `personal.jsonl` still exist — nothing else commits those counts.

Much of it can be reconstructed from git: `index.json` is committed on every
run with one entry per line, so `history.py --from-git` recovers a row for
each day it changed, measuring ages against that commit's own date. A
recovered row carries only what its commit still holds — the library and
personal tiers were never committed, so those fields are absent rather than
guessed — and it never overwrites a row that already exists. What cannot be
recovered at all is anything read from a file that is replaced rather than
versioned once the databases moved to release cuts.

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

`--recount` and `--summarize` are backfills for fields added after rows were
already written. `--summarize` reads raw `flake.lock` files rather than
re-pinning, which avoids downloading a tree per flake, but
`raw.githubusercontent.com` throttles sustained traffic: the first backfill
of 11,429 rows took 42 minutes at 16 jobs, not the few minutes a short
sample suggests. Run it locally, not in CI.

## Continuous integration

`update.yml` runs the pipeline daily, cuts a data release for the databases
that moved, and commits the regenerated index and the repointed
`data-pins.json` to `main`. The upload happens before the commit: a commit
that fails afterwards leaves unreferenced assets on a dated tag, which the
next run re-cuts, while the reverse order would commit a pin naming bytes
that were never uploaded. That ordering is also what lets the cut's notes
diff the new index against `HEAD`.

The `concurrency` group keeps two runs from writing to `main` at once, but a
person can still push during the twenty-five minutes a run takes, and a
rejected push would discard the whole run. The push therefore rebases onto
the current tip and retries once. Every other artefact would be regenerated
tomorrow; `history.jsonl` would not, since `history.py` keys rows by date and
`--from-git` recovers them from `index.json`'s commit history — the commit
that was lost.

`check.yml` runs on pushes and pull requests: it fetches the pinned
databases, locks the flake, regenerates the index and fails on any
difference, checks that the regenerated `pins.jsonl` still matches its pin,
runs `nix flake check`, and evaluates a random sample of flakes for the job
summary. `pages.yml` builds and deploys the site.
