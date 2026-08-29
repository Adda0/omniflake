{
  description = "omniflake: thousands of Nix flakes behind one input, fetched lazily";

  # The only real inputs. Every other flake is a pin in index.json and is
  # evaluated from its own lock file by lib/load.nix when first touched.
  # These five are the ones substituted into every subflake by default,
  # so `inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs"` reaches all
  # of them at once.
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    systems.url = "github:nix-systems/default";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-compat.url = "github:edolstra/flake-compat";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      systems,
      flake-parts,
      flake-compat,
    }:
    let
      inherit (builtins)
        attrNames
        fromJSON
        length
        listToAttrs
        readFile
        replaceStrings
        ;

      # One entry per flake: its `locked` attributes and whether a computed
      # lock is stored under locks/. Reading the index forces no fetch.
      index = fromJSON (readFile ./index.json);
      names = attrNames index;

      # Inputs replaced by name in every subflake, at every depth. Exact
      # names only: `nixpkgs-stable` is left on the pin its author chose.
      foundations = {
        inherit
          nixpkgs
          flake-utils
          systems
          flake-parts
          flake-compat
          ;
      };

      load = import ./lib/load.nix;

      # Mirrors lock_key in tools/pin.py: stored locks are named after the
      # revision, or the narHash for the rare input type without one.
      lockKey =
        locked: if locked ? rev then locked.rev else replaceStrings [ "/" "=" ] [ "_" "" ] locked.narHash;

      storedLock =
        entry:
        if entry.lock or false then
          fromJSON (readFile (./locks + "/${lockKey entry.locked}.json"))
        else
          null;

      loadWith =
        overrides: name:
        let
          entry = index.${name};
        in
        load {
          inherit (entry) locked;
          lock = storedLock entry;
          inherit overrides;
        };

      # Every flake under one policy, as a lazy attribute set.
      withOverrides =
        overrides:
        listToAttrs (
          map (name: {
            inherit name;
            value = loadWith overrides name;
          }) names
        );

      # The repository's own tooling, per system. Nothing below is touched
      # by a consumer reaching for a subflake.
      devSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems =
        f:
        listToAttrs (
          map (system: {
            name = system;
            value = f system;
          }) devSystems
        );
      pkgsFor = system: nixpkgs.legacyPackages.${system};

      # The formatter comes out of the index: this repository is its own
      # first consumer, and no development-only input reaches anyone's lock.
      treefmtFor =
        system:
        import ./nix/formatter.nix {
          inherit (self.flakes) treefmt-nix;
          pkgs = pkgsFor system;
        };
    in
    {
      # omniflake.flakes.<name>: the flake with the five foundations
      # substituted, which is what modules and overlays want.
      flakes = withOverrides foundations;

      # omniflake.pinned.<name>: the flake exactly as its author locked it.
      pinned = withOverrides { };

      lib = {
        # Metadata that forces no fetch.
        inherit names foundations;
        count = length names;

        # omniflake.lib.withOverrides { nixpkgs = ...; nixpkgs-stable = ...; }
        # gives every flake under a policy of your own.
        inherit withOverrides;

        # omniflake.lib.load "nh" { nixpkgs = pkgs-stable; } for a single one.
        load = name: overrides: loadWith overrides name;
      };

      formatter = forAllSystems (system: (treefmtFor system).config.build.wrapper);

      # `nix build .#site` is the tree the pages workflow deploys; `.#docs`
      # is the rendered documentation alone.
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          site = import ./nix/site.nix { inherit pkgs self; };
          docs = import ./nix/docs.nix { inherit pkgs; };
        }
      );

      checks = forAllSystems (
        system:
        import ./nix/checks.nix {
          inherit self system;
          pkgs = pkgsFor system;
          treefmt = treefmtFor system;
        }
      );

      # `nix run .#update`, `nix run .#pin -- --jobs 32`, `nix run .#generate`.
      apps = forAllSystems (
        system:
        let
          tools = import ./nix/tools.nix { pkgs = pkgsFor system; };
        in
        builtins.mapAttrs (name: description: {
          type = "app";
          program = "${tools.wrappers.${name}}/bin/${name}";
          meta = { inherit description; };
        }) tools.descriptions
        // {
          # `nix run .#serve [port]` — the built site on a local port.
          serve = {
            type = "app";
            program = "${
              import ./nix/serve.nix {
                pkgs = pkgsFor system;
                site = self.packages.${system}.site;
              }
            }/bin/serve-site";
            meta.description = "Serve the built site locally for testing";
          };
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          tools = import ./nix/tools.nix { inherit pkgs; };
        in
        {
          default = pkgs.mkShellNoCC {
            packages = tools.deps ++ [ pkgs.gh ];
          };
        }
      );
    };
}
