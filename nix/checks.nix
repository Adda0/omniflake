# `nix flake check` runs these.
#
# The eval tests return a small summary only after their assertions hold,
# so serialising the summary into a derivation makes *evaluation* the
# test; the build step just writes it out.
{
  self,
  pkgs,
  system,
  treefmt,
}:
let
  evalTest =
    name: file:
    pkgs.runCommand name {
      summary = builtins.toJSON (import file { inherit self system; });
    } ''echo "$summary" > $out'';
in
{
  # Pure assertions over index.json and locks/: no network.
  index = evalTest "test-index" ../tests/index.nix;

  # The loader on real flakes: fetches a few trees at evaluation time.
  loader = evalTest "test-loader" ../tests/loader.nix;

  formatting = treefmt.config.build.check self;
}
