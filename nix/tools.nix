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
    # fetch-data.sh pulls the pinned databases over HTTP.
    pkgs.curl
  ];

  # The entry point interpolates ../tools, so a wrapper runs a store
  # snapshot of the scripts taken when the flake was evaluated, not the
  # files in the caller's checkout. The pipeline mutates only the data
  # files, never the scripts, so the snapshot is safe; editing a script
  # needs a re-run of `nix run` to be picked up.
  # The guard is index.json, not one of the databases: those are fetched
  # rather than committed, so a fresh checkout does not have them yet and
  # fetch-data is precisely the tool that runs when they are absent.
  wrap =
    name: entry: extra:
    pkgs.writeShellApplication {
      inherit name;
      runtimeInputs = deps ++ extra;
      text = ''
        if [ ! -f "$PWD/index.json" ]; then
          echo "${name}: run this from an omniflake checkout (no index.json in $PWD)" >&2
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
    classify = {
      description = "Split resolved flakes into library and personal tiers";
      entry = "python3 ${../tools}/classify.py";
    };
    sample = {
      description = "Evaluate a random sample of indexed flakes";
      entry = "python3 ${../tools}/sample.py";
    };
    verify = {
      description = "Re-derive and evaluate pins changed since a base revision";
      entry = "python3 ${../tools}/verify.py";
    };
    history = {
      description = "Append today's aggregate row to history.jsonl";
      entry = "python3 ${../tools}/history.py";
    };
    fetch-data = {
      description = "Download the databases data-pins.json pins into the checkout";
      entry = "bash ${../tools}/fetch-data.sh";
    };
    release-notes = {
      description = "Render the notes for a data release cut";
      entry = "python3 ${../tools}/release-notes.py";
    };
    cut-data-release = {
      description = "Upload changed databases to a dated release and repoint the pins";
      entry = "bash ${../tools}/cut-data-release.sh";
      extra = [ pkgs.gh ];
    };
    bump-data-pin = {
      description = "Repoint data-pins.json at a dated release cut";
      entry = "bash ${../tools}/bump-data-pin.sh";
    };
  };
in
{
  inherit deps;

  descriptions = builtins.mapAttrs (_: t: t.description) tools;

  # { <tool> = <wrapped executable>; }
  wrappers = builtins.mapAttrs (name: t: wrap name t.entry (t.extra or [ ])) tools;
}
