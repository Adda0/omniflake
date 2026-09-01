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

  # Every flake is reachable by its qualified and nested names. Asks about
  # attribute keys only, so nothing is fetched.
  names = evalTest "test-names" ../tests/names.nix;

  # The Python in tools/. These cover the pipeline's decision functions —
  # which failures to re-attempt, which candidates to re-check, how the
  # candidate pool merges — so they work on plain data and run neither Nix
  # nor the network.
  tools = pkgs.runCommand "test-tools" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    cp -r ${../tools} tools
    cp -r ${../tests} tests
    python3 -m unittest discover -s tests -p 'test_*.py' -v
    touch $out
  '';

  formatting = treefmt.config.build.check self;
}
