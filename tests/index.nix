# Checks that index.json is internally consistent, without touching the
# network: every entry is fetchable in pure mode, every stored lock an
# entry points at exists and parses, and no stored lock is orphaned.
{ self, ... }:
let
  inherit (builtins)
    attrNames
    filter
    length
    listToAttrs
    pathExists
    readDir
    readFile
    fromJSON
    ;

  index = fromJSON (readFile ../index.json);
  names = attrNames index;

  # Mirrors lock_key in tools/pin.py and lockKey in flake.nix.
  lockKey =
    locked:
    if locked ? rev then locked.rev else builtins.replaceStrings [ "/" "=" ] [ "_" "" ] locked.narHash;

  # A pin must carry what fetchTree needs to be considered locked in pure
  # evaluation: a type, and a narHash. Anything else is the fetcher's business.
  unfetchable = filter (name: !(index.${name}.locked ? type && index.${name}.locked ? narHash)) names;

  withLock = filter (name: index.${name}.lock or false) names;
  missingLock = filter (
    name: !pathExists (../locks + "/${lockKey index.${name}.locked}.json")
  ) withLock;

  # Every stored lock parses as a version 7 lock with a root node.
  lockFiles = attrNames (readDir ../locks);
  malformed = filter (
    file:
    let
      lock = fromJSON (readFile (../locks + "/${file}"));
    in
    !(lock.version or 0 == 7 && lock.nodes ? ${lock.root or "root"})
  ) lockFiles;

  inUse = listToAttrs (
    map (name: {
      name = "${lockKey index.${name}.locked}.json";
      value = true;
    }) withLock
  );
  orphaned = filter (file: !(inUse ? ${file})) lockFiles;

  # Every override key unification uses has to name an indexed flake, or
  # `unified` fails on an attribute that is not there.
  unifyNames = self.lib.unifyNames;
  danglingUnifyKey = filter (name: !(index ? ${name})) unifyNames;

  # flake.nix and the index must agree on the count.
  count = self.lib.count;
in
assert unfetchable == [ ];
assert missingLock == [ ];
assert malformed == [ ];
assert orphaned == [ ];
assert danglingUnifyKey == [ ];
assert count == length names;
{
  flakes = count;
  storedLocks = length withLock;
  unifyKeys = length unifyNames;
}
