# Building the index

```console
$ ./tools/update.sh              # discover new flakes, keep existing pins
$ ./tools/update.sh --refresh    # also re-pin everything already known
$ ./tools/update.sh --no-harvest # regenerate and lock from current data
```

`OMNIFLAKE_TOP=300` limits the built tier to the top N by stars.

| tool | what it does |
| --- | --- |
| `harvest.py` | GitHub search by `language:Nix` and topic, partitioned by star range and push date to stay under the 1000-result cap |
| `manual.py` | flakes listed by hand in `manual.txt`, including non-GitHub ones |
| `resolve.py` | one GraphQL round trip per 40 repos: HEAD commit, whether `flake.nix` exists, and `flake.lock` |
| `classify.py` | splits off personal machine configurations |
| `generate.py` | emits `flake.nix` with pinned revisions and `follows` |
| `lock.sh` | locks, quarantining members that cannot be locked |
| `audit.py` | finds subflakes that lock here but break consumers |
| `deepen.py` | derives nested `follows` from a pass-1 lock |

`resolved.jsonl` is a committed database that is added to, not regenerated.
Rediscovering everything on each run wastes hundreds of API calls and risks
reassigning names.

## Two passes

Pass 1 locks shallowly, purely to produce a lock whose transitive graph can be
read. `deepen.py` walks it and emits nested `follows`. Pass 2 relocks with those.

Locking is the slow step: Nix must fetch every subflake's source to read its
`flake.nix` and discover its inputs. Consumers never pay this.
