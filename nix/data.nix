# The databases that build the site, fetched rather than carried.
#
# resolved.jsonl, pins.jsonl and candidates.jsonl are pipeline state and
# site-build input. Nothing evaluates them: `flake.nix` reads index.json and
# locks/, and that is the whole of what a consumer's evaluation touches. They
# used to be committed anyway, which put 10.7 MB — 65% of the gzipped
# tarball — into every consumer's fetch. They now live on dated release
# cuts, addressed by data-pins.json.
#
# The pin is what ties them to a commit. A release asset is a mutable
# pointer: a tag plus a name, re-uploadable at will. Recording {tag, narHash}
# per file in a committed manifest makes the pair immutable in the only sense
# that matters — a swapped asset fails the hash and the build stops.
#
# Returns { "<file>" = <store path>; }, one entry per pinned file.
{ pkgs }:
let
  fetchArtifact = import ./fetch-artifact.nix { inherit pkgs; };
  pins = builtins.fromJSON (builtins.readFile ../data-pins.json);
in
builtins.mapAttrs (
  name: pin:
  fetchArtifact {
    url = "${pins.baseUrl}/${pin.tag}/${name}";
    hash = pin.narHash;
  }
) pins.files
