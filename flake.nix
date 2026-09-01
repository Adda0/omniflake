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
        filter
        fromJSON
        groupBy
        length
        listToAttrs
        mapAttrs
        readFile
        replaceStrings
        ;

      # One entry per flake: its `locked` attributes and whether a computed
      # lock is stored under locks/. Reading the index forces no fetch.
      index = fromJSON (readFile ./index.json);
      names = attrNames index;

      # The names `unified` substitutes by input name, which is not every
      # name in the index. An override key claims that an input called that
      # means this flake, and a name 26 repositories claim means none of
      # them. tools/generate.py writes the file; see docs/unification.md.
      unifyNames = fromJSON (readFile ./unify.json);

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

      # A flake's qualified name: its flake reference without the revision.
      # This is what the index knows a flake as no matter which attribute
      # name it was given, so it identifies one repository and only ever
      # one, where a bare name is contested by up to 78 of them.
      qualified =
        name:
        let
          locked = index.${name}.locked;
        in
        "${locked.type}:${locked.owner}/${locked.repo}";

      # One policy's flakes keyed by qualified name. A bare name is a legal
      # Nix attribute name and a qualified one carries a colon, so the two
      # key spaces share no key and the result merges into the policy set.
      byQualifiedName =
        policy:
        listToAttrs (
          map (name: {
            name = qualified name;
            value = policy.${name};
          }) names
        );

      # One policy's flakes on one forge, as <owner>.<repo>. Same flakes and
      # the same thunks as the two spellings above; what changes is that the
      # owner is an attribute you can complete rather than half of a string.
      byOwner =
        forge: policy:
        mapAttrs
          (
            _: forgeNames:
            listToAttrs (
              map (name: {
                name = index.${name}.locked.repo;
                value = policy.${name};
              }) forgeNames
            )
          )
          (
            groupBy (name: index.${name}.locked.owner) (filter (name: index.${name}.locked.type == forge) names)
          );

      # Every flake under one policy, plus every flake whose name the index
      # is sure of overriding that name: a graph reaches one home-manager,
      # one disko, one treefmt-nix, rather than the revision each author
      # happened to lock.
      #
      # The overrides are the set being defined, so a substituted flake's
      # own graph is unified too, at any depth, rather than stopping at the
      # five foundations.
      #
      # The foundations win over the index, and the caller's `extra` wins
      # over both. All five foundation names are indexed flakes as well, and
      # taking them from the index would quietly break the one thing a
      # consumer controls: `inputs.omniflake.inputs.nixpkgs.follows` reaches
      # a declared input and nothing else.
      unifyAll =
        extra:
        let
          fromIndex = listToAttrs (
            map (name: {
              inherit name;
              value = all.${name};
            }) unifyNames
          );
          all = withOverrides (fromIndex // foundations // extra);
        in
        all;

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
      # The three policies, each keyed by attribute name. Bound here rather
      # than in the outputs because the qualified spellings below hand out
      # the same thunks, and a flake evaluated twice is fetched twice.
      flakesByName = withOverrides foundations;
      pinnedByName = withOverrides { };
      unifiedByName = unifyAll { };
    in
    {
      # omniflake.flakes.<name>: the flake with the five foundations
      # substituted, which is what modules and overlays want.
      # omniflake.flakes."github:<owner>/<repo>": the same flake, named in
      # full. Every flake answers to this; only some have a bare name.
      flakes = flakesByName // byQualifiedName flakesByName;

      # omniflake.pinned.<name>: the flake exactly as its author locked it.
      pinned = pinnedByName // byQualifiedName pinnedByName;

      # omniflake.unified.<name>: the foundations, and every other input
      # whose name the index knows. One copy of each flake in the graph,
      # at the cost of the revision its author chose.
      unified = unifiedByName // byQualifiedName unifiedByName;

      # omniflake.github.<policy>.<owner>.<repo>: the third spelling, for
      # tab completion in a repl and for reading an owner's flakes off one
      # attribute set. The forge is a root attribute written out here, not
      # derived from the index, so the day a gitlab: line enters manual.txt
      # a root attribute does not appear on its own.
      github = {
        flakes = byOwner "github" flakesByName;
        pinned = byOwner "github" pinnedByName;
        unified = byOwner "github" unifiedByName;
      };

      lib = {
        # Metadata that forces no fetch.
        inherit names foundations;

        # The names `unified` substitutes by input name; see unifyAll.
        unifyNames = unifyNames;
        count = length names;

        # omniflake.lib.withOverrides { nixpkgs = ...; nixpkgs-stable = ...; }
        # gives every flake under a policy of your own.
        inherit withOverrides;

        # omniflake.lib.unifyAll { } is `unified`; anything passed wins over
        # the index and the foundations both.
        inherit unifyAll;

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
          # `nix run .#serve [port]`: the built site on a local port.
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
