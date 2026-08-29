# Adding a flake

Search only finds what people remembered to tag, and it cannot see GitLab or
sourcehut at all. `manual.txt` is committed and read on every run:

```
nix-community/disko          a GitHub repo, pinned to its default branch
github:owner/repo/v1.2.3     pinned to a ref you choose
gitlab:owner/repo            anything else Nix can fetch
```

A bare `owner/repo` becomes a candidate and is pinned by `tools/resolve.py` like
any harvested repo. Anything else is resolved with `nix flake metadata` and
pinned to an exact revision.

Open a PR adding a line. Then:

```console
$ ./tools/update.sh --no-harvest
```

## Names are API

An attribute name is derived from the repository name, with the owner appended
on collision, and **never changes once assigned**. A repo that later gains stars
cannot take a bare name from the repo that holds it, because every consumer
writing `omniflake.flakes.<name>` would silently get a different flake.
