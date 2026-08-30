#!/usr/bin/env python3
"""Pin every library flake with Nix itself, one process per flake, in parallel.

A pin is what `builtins.fetchTree` needs to fetch a flake purely: the
`locked` attribute set Nix produces for an exact revision (type, owner,
repo, rev, narHash, lastModified). The only way to obtain a narHash is to
download the tree, and `nix flake metadata --json` does exactly that. It
also returns `locks`, the lock file Nix computes for the flake's own
inputs: identical to the committed flake.lock when that lock is current,
and a repaired one (stale inputs re-resolved by Nix's rules) when it is
not. That computed lock is stored under locks/ only when it differs, so
the loader can fall back to the committed file for the common case.

This replaces `nix flake lock` over one enormous flake.nix, which fetched
the same trees serially and aborted on the first member that could not be
locked. Here every flake is independent: failures are recorded with their
reason and the rest proceed.

Incremental: a pin is keyed by its exact flake reference, and a revision
never changes, so an existing pin is never recomputed. Re-running after a
crash or with a grown library only touches what is new.

Reads library rows ({name, owner, repo, rev, [url], stars, ...}) and writes:
    pins.jsonl      {name, ref, locked, lock: bool, lock_nodes}  per success
    failures.jsonl  {name, ref, error}                appended per failure
    locks/REV.json  Nix's computed lock, when it differs from the committed one

Stored locks are keyed by revision, not by attribute name: a revision is
immutable, two forks pinned at the same commit share one file, and
renaming a flake cannot orphan its lock.
"""

import argparse, concurrent.futures, json, os, subprocess, sys, threading, time

# Per-flake wall clock bound. A nixpkgs fork takes about a minute to
# download and hash; anything past this is stuck, not slow.
TIMEOUT_SECONDS = 900
# Retried once after a pause, since GitHub answers bursts with 429/503.
RETRY_DELAY_SECONDS = 30
# How much of a failing command's stderr is kept for the record.
ERROR_TAIL_CHARS = 600

# Attributes Nix adds to `locked` at fetch time that a lock file omits.
INTERNAL_LOCKED_ATTRS = {"__final"}

# pipe-operators is a parse-time feature some flake.nix files already use;
# without it Nix cannot even read their inputs. A consumer evaluating such
# a flake needs the feature too, which docs/caveats.md says.
NIX_CONFIG_FEATURES = "experimental-features = nix-command flakes pipe-operators"

# Nix unpacks every tarball into a git-backed cache and writes one packfile
# per tarball, never repacking. libgit2 consults every pack index on every
# object lookup, so once tens of thousands of packs have accumulated each
# fetch slows to a crawl: a run measured 190 pins/minute at the start and
# 3/minute at 60,000 packs. Repacking into one pack restores the rate.
TARBALL_CACHE_DIR = "nix/tarball-cache-v2"
REPACK_EVERY = 500
REPACK_THREADS = 32

# Without an access token Nix downloads GitHub tarballs from the archive
# endpoint, which is not subject to the 5000/hour REST API quota that
# api.github.com/repos/.../tarball counts against. Twelve thousand
# downloads in an hour are only possible this way.
NIX_CONFIG_NO_TOKEN = "access-tokens ="


def read_jsonl(path):
    """Yield parsed rows, tolerating comments and the odd corrupt line."""
    if not path or not os.path.exists(path):
        return
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"warning: {path}:{lineno}: skipping malformed line",
                    file=sys.stderr,
                )


def flake_ref(row):
    """The exact reference a row is pinned at. Manual rows carry a url."""
    return row.get("url") or f"github:{row['owner']}/{row['repo']}/{row['rev']}"


def nix_env(use_token):
    """The environment every nix invocation runs under."""
    env = dict(os.environ)
    config = [NIX_CONFIG_FEATURES]
    if not use_token:
        config.append(NIX_CONFIG_NO_TOKEN)
    elif env.get("GH_TOKEN") or env.get("GITHUB_TOKEN"):
        # In CI the token is in the environment, not in nix.conf.
        token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
        config.append(f"access-tokens = github.com={token}")
    env["NIX_CONFIG"] = "\n".join(config)
    return env


def run_metadata(ref, use_token):
    """Run `nix flake metadata --json` for one ref; return (json or None, error)."""
    env = nix_env(use_token)
    # Registries stay enabled: an input written as a bare "nixpkgs" is an
    # indirect reference that Nix resolves through the global registry, and
    # a lock computed without one would fail where `nix flake lock` succeeds.
    cmd = ["nix", "flake", "metadata", "--json", "--no-write-lock-file", ref]
    for attempt in range(2):
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, env=env
            )
        except subprocess.TimeoutExpired:
            return None, f"timeout after {TIMEOUT_SECONDS}s"
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout), ""
            except json.JSONDecodeError as e:
                return None, f"unparseable metadata: {e}"
        err = proc.stderr.strip()
        # A throttled GitHub is the one failure worth waiting out.
        transient = any(
            s in err
            for s in (
                "HTTP error 429",
                "HTTP error 503",
                "HTTP error 502",
                "Could not resolve host",
                "Failed to connect",
                "rate limit",
            )
        )
        if not transient or attempt == 1:
            return None, err[-ERROR_TAIL_CHARS:]
        time.sleep(RETRY_DELAY_SECONDS)
    return None, "unreachable"


def tarball_cache():
    """Nix's git-backed tarball cache, or None if it does not exist yet."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, TARBALL_CACHE_DIR)
    return path if os.path.isdir(os.path.join(path, "objects")) else None


def repack_tarball_cache():
    """Fold the tarball cache's packs into a geometric progression.

    Not `git repack -a -d`: the cache has no refs, Nix addresses its trees by
    hash, so to git every object is unreachable and that command packs
    nothing and then deletes everything. `--geometric` works from the list
    of packs instead of from reachability, and being incremental it costs
    little as the cache grows: 19,655 packs folded into one in 45 seconds.

    Safe to run while Nix processes use the cache: the new pack is complete
    before any old one is removed, and a reader holding an old pack open
    keeps it until done.
    """
    path = tarball_cache()
    if path is None:
        return
    packs = os.path.join(path, "objects", "pack")
    if not os.path.isdir(packs):
        return
    before = sum(1 for f in os.listdir(packs) if f.endswith(".pack"))
    if before < 2:
        return

    started = time.time()
    proc = subprocess.run(
        [
            "git",
            "-C",
            path,
            "repack",
            "--geometric=2",
            "-d",
            "-q",
            "--window=0",
            f"--threads={REPACK_THREADS}",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"warning: repack failed: {proc.stderr.strip()[-200:]}", file=sys.stderr)
        return
    after = sum(1 for f in os.listdir(packs) if f.endswith(".pack"))
    print(
        f"    repacked tarball cache: {before} packs -> {after} in {time.time() - started:.0f}s",
        file=sys.stderr,
        flush=True,
    )


def committed_lock(store_path, locked, env):
    """The flake.lock shipped in the fetched tree, or None if absent/invalid.

    `nix flake metadata` reports a store path, but a Nix with lazy trees
    never materialises it, so the file is read through fetchTree instead
    when the path is not on disk. The tree is already in the fetch cache,
    so this costs an evaluation and no download.
    """
    path = os.path.join(store_path, "flake.lock")
    if os.path.isdir(store_path):
        if not os.path.exists(path):
            return None
        try:
            with open(path) as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    expr = (
        "let t = builtins.fetchTree (builtins.fromJSON %s); "
        'in if builtins.pathExists (t + "/flake.lock") '
        'then builtins.readFile (t + "/flake.lock") else null'
    ) % json.dumps(json.dumps(locked))
    proc = subprocess.run(
        ["nix", "eval", "--json", "--expr", expr],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        env=env,
    )
    if proc.returncode != 0:
        return None
    try:
        text = json.loads(proc.stdout)
        return json.loads(text) if text else None
    except (json.JSONDecodeError, TypeError):
        return None


def lock_key(locked):
    """The file name a computed lock is stored under: the revision, or the
    narHash for the rare input type that has none."""
    if locked.get("rev"):
        return locked["rev"]
    return locked["narHash"].replace("/", "_").replace("=", "")


def write_lock(locks_dir, key, lock):
    """Store a computed lock the way Nix formats one: two-space, sorted keys."""
    os.makedirs(locks_dir, exist_ok=True)
    path = os.path.join(locks_dir, f"{key}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(lock, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def pin_one(row, use_token, locks_dir):
    """Pin a single row. Returns ("ok", pin) or ("fail", failure)."""
    ref = flake_ref(row)
    meta, err = run_metadata(ref, use_token)
    if meta is None:
        return "fail", {"name": row["name"], "ref": ref, "error": err}

    locked = {k: v for k, v in meta["locked"].items() if k not in INTERNAL_LOCKED_ATTRS}
    nix_lock = meta.get("locks") or {}
    shipped = committed_lock(meta["path"], locked, nix_env(use_token))

    # The committed lock is authoritative whenever Nix agrees with it. A
    # stored copy is needed only where Nix had to repair something, or
    # where the flake ships no lock at all despite having inputs.
    needs_lock = shipped != nix_lock
    if needs_lock:
        write_lock(locks_dir, lock_key(locked), nix_lock)

    return "ok", {
        "name": row["name"],
        "ref": ref,
        "locked": locked,
        "lock": needs_lock,
        # The size of the graph the loader will walk: every node of the lock
        # it uses, committed or computed, except the root.
        "lock_nodes": max(len(nix_lock.get("nodes", {})) - 1, 0),
    }


def recount(args):
    """Fill in lock_nodes for pins recorded before it existed. The tree is
    in the fetch cache for anything pinned on this machine, so this is
    mostly evaluation."""
    pins = list(read_jsonl(args.pins))
    todo = [p for p in pins if "lock_nodes" not in p]
    print(
        f"==> {len(pins)} pins, {len(todo)} without lock_nodes",
        file=sys.stderr,
        flush=True,
    )

    def one(pin):
        meta, err = run_metadata(pin["ref"], args.use_token)
        if meta is None:
            return pin, None
        return pin, max(len((meta.get("locks") or {}).get("nodes", {})) - 1, 0)

    done = failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for pin, count in pool.map(one, todo):
            if count is None:
                failed += 1
            else:
                pin["lock_nodes"] = count
            done += 1
            if done % 200 == 0:
                print(
                    f"    {done}/{len(todo)} ({failed} failed)",
                    file=sys.stderr,
                    flush=True,
                )

    tmp = args.pins + ".tmp"
    with open(tmp, "w") as fh:
        for pin in pins:
            fh.write(json.dumps(pin, sort_keys=True) + "\n")
    os.replace(tmp, args.pins)
    print(f"==> recounted {done - failed}, failed {failed}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="library.jsonl")
    ap.add_argument("--pins", default="pins.jsonl")
    ap.add_argument("--failures", default="failures.jsonl")
    ap.add_argument("--locks", default="locks")
    ap.add_argument("--blocklist", default="blocklist.txt")
    ap.add_argument("--jobs", type=int, default=32)
    ap.add_argument("--limit", type=int, help="pin at most N new flakes")
    ap.add_argument(
        "--retry-failed",
        action="store_true",
        help="re-attempt refs recorded in the failures file",
    )
    ap.add_argument(
        "--recount",
        action="store_true",
        help="fill in lock_nodes for pins that lack it, then exit",
    )
    ap.add_argument(
        "--repack-every",
        type=int,
        default=REPACK_EVERY,
        help="repack Nix's tarball cache after this many pins (0 disables)",
    )
    ap.add_argument(
        "--use-token",
        action="store_true",
        help="keep Nix's access-tokens, or use $GH_TOKEN (subject to the API quota)",
    )
    args = ap.parse_args()

    if args.recount:
        recount(args)
        return

    blocked = set()
    if os.path.exists(args.blocklist):
        blocked = {
            l.strip()
            for l in open(args.blocklist)
            if l.strip() and not l.startswith("#")
        }

    # Everything already decided, by exact ref. Failures are remembered so
    # a nightly run does not re-download the same broken flakes forever.
    done = {p["ref"] for p in read_jsonl(args.pins)}
    failed = (
        set() if args.retry_failed else {f["ref"] for f in read_jsonl(args.failures)}
    )

    todo = []
    for row in read_jsonl(args.library):
        if row["name"] in blocked:
            continue
        ref = flake_ref(row)
        if ref in done or ref in failed:
            continue
        todo.append(row)
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"==> {len(done)} pinned, {len(failed)} known failures, {len(todo)} to pin",
        file=sys.stderr,
        flush=True,
    )

    # Results are appended as they arrive, so a killed run loses nothing.
    lock = threading.Lock()
    counts = {"ok": 0, "fail": 0}
    pins_fh = open(args.pins, "a")
    fail_fh = open(args.failures, "a")

    def record(kind, payload):
        with lock:
            fh = pins_fh if kind == "ok" else fail_fh
            fh.write(json.dumps(payload, sort_keys=True) + "\n")
            fh.flush()
            counts[kind] += 1
            total = counts["ok"] + counts["fail"]
            if total % 100 == 0 or total == len(todo):
                print(
                    f"    {total}/{len(todo)} ({counts['fail']} failed)",
                    file=sys.stderr,
                    flush=True,
                )

    # One repack at a time, off the worker threads, so a slow repack never
    # stalls the pinning and two never race each other.
    repacker: dict = {"thread": None}

    def maybe_repack(done):
        if not args.repack_every or done % args.repack_every:
            return
        if repacker["thread"] is not None and repacker["thread"].is_alive():
            return
        repacker["thread"] = threading.Thread(target=repack_tarball_cache, daemon=True)
        repacker["thread"].start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [
            pool.submit(pin_one, row, args.use_token, args.locks) for row in todo
        ]
        for fut in concurrent.futures.as_completed(futures):
            record(*fut.result())
            maybe_repack(counts["ok"] + counts["fail"])

    if repacker["thread"] is not None:
        repacker["thread"].join()

    pins_fh.close()
    fail_fh.close()
    print(f"==> pinned {counts['ok']}, failed {counts['fail']}", file=sys.stderr)


if __name__ == "__main__":
    main()
