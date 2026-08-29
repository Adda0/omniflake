# `nix fmt`, through treefmt-nix, taken from the index itself: the
# formatter is `omniflake.flakes.treefmt-nix`, so the repository is its own
# first consumer and no development-only input reaches anyone's lock file.
{ treefmt-nix, pkgs }:
treefmt-nix.lib.evalModule pkgs {
  projectRootFile = "flake.nix";

  programs.nixfmt.enable = true;

  # The scripts in tools/. black rather than a linter: the point is that
  # nobody argues about where a call wraps.
  programs.black.enable = true;

  # Markdown and the workflow files, at the width the docs are written to.
  # proseWrap stays at its default of preserving line breaks: the docs are
  # hand-wrapped prose, and reflowing them makes every diff a whole-file diff.
  programs.prettier.enable = true;
  settings.formatter.prettier = {
    options = [
      "--print-width"
      "80"
    ];
    includes = [
      "*.md"
      "*.yml"
    ];
  };

  # Generated data, and stored lock files written the way Nix writes them.
  settings.global.excludes = [
    "index.json"
    "locks/*"
    "*.jsonl"
    "flake.lock"
  ];
}
