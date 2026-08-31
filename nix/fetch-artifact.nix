# One pinned database file, as a fixed-output derivation.
#
# fetchurl, not fetchTree: fetchTree downloads during *evaluation*, and
# `nix flake show` and `nix flake check` evaluate packages.<system>.site
# without building it. An eval-time fetch would put a network round trip in
# the path of both, for anyone pointing them at the flake's own URL. A
# fixed-output derivation keeps evaluation pure and offline, and the bytes
# move only when something actually builds the site.
#
# recursiveHash: data-pins.json records what `nix hash path` computes, which
# is the NAR hash of the file, not the flat hash fetchurl checks by default.
#
# Separate from data.nix so a caller can aim this exact fetcher at one file.
{ pkgs }:
{ url, hash }:
pkgs.fetchurl {
  inherit url hash;
  recursiveHash = true;
}
