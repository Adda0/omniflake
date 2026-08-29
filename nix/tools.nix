# The scripts in tools/, as things a caller can run.
#
# `nix run .#update` executes a copy of tools/ out of the store, but every
# script rewrites resolved.jsonl, pins.jsonl and index.json in place, so
# they need a checkout to act on. The wrapper runs them in the caller's
# directory and refuses to guess when that is not a checkout.
{ pkgs }:
let
  # What tools/*.sh and tools/*.py reach for. `nix` is deliberately absent:
  # pin.py calls `nix flake metadata` against the caller's own store and
  # configuration, so the host's nix is the correct one to use.
  deps = [
    pkgs.bash
    pkgs.python3
    pkgs.gitMinimal
    pkgs.coreutils
    pkgs.gnugrep
  ];

  wrap =
    name: entry:
    pkgs.writeShellApplication {
      inherit name;
      runtimeInputs = deps;
      text = ''
        if [ ! -f "$PWD/resolved.jsonl" ]; then
          echo "${name}: run this from an omniflake checkout (no resolved.jsonl in $PWD)" >&2
          exit 1
        fi
        exec ${entry} "$@"
      '';
    };

  tools = {
    update = {
      description = "Harvest, resolve, pin and regenerate index.json";
      entry = "bash ${../tools}/update.sh";
    };
    pin = {
      description = "Pin library flakes with nix flake metadata, in parallel";
      entry = "python3 ${../tools}/pin.py";
    };
    generate = {
      description = "Regenerate index.json from the pins";
      entry = "python3 ${../tools}/generate.py";
    };
  };
in
{
  inherit deps;

  descriptions = builtins.mapAttrs (_: t: t.description) tools;

  # { <tool> = <wrapped executable>; }
  wrappers = builtins.mapAttrs (name: t: wrap name t.entry) tools;
}
