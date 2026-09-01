# How to use it

## Add the input

```nix
{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.omniflake.url = "github:fzakaria/omniflake";
  inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs";
}
```

The `follows` line makes your `nixpkgs` the one substituted into every
indexed flake. Without it, omniflake's own pin of `nixos-unstable` is used.

`nix flake lock` adds six nodes: omniflake and its five inputs. Indexed
flakes are fetched only when evaluated.

## Modules

```nix
{
  outputs = { self, nixpkgs, omniflake, ... }: {
    nixosConfigurations.host = nixpkgs.lib.nixosSystem {
      modules = [
        omniflake.flakes.home-manager.nixosModules.home-manager
        omniflake.flakes.disko.nixosModules.disko
        omniflake.flakes.sops-nix.nixosModules.sops
        ./configuration.nix
      ];
    };
  };
}
```

Home Manager and nix-darwin modules work the same way:

```nix
home-manager.users.me = {
  imports = [ omniflake.flakes.nixvim.homeManagerModules.nixvim ];
};
```

## Overlays and packages

```nix
{
  nixpkgs.overlays = [ omniflake.flakes.nur.overlays.default ];

  environment.systemPackages = [
    omniflake.flakes.nh.packages.${pkgs.system}.default
  ];
}
```

## From the command line

Number of indexed flakes:

```console
$ nix eval github:fzakaria/omniflake#lib.count
```

All attribute names:

```console
$ nix eval --json github:fzakaria/omniflake#lib.names
```

Run a package from an indexed flake:

```console
$ nix run 'github:fzakaria/omniflake#flakes.nh.packages.x86_64-linux.default'
```

Open a shell with one:

```console
$ nix shell 'github:fzakaria/omniflake#flakes.nixos-generators.packages.x86_64-linux.default'
```

Inspect a flake's inputs as they will be evaluated:

```console
$ nix eval --json 'github:fzakaria/omniflake#flakes.agenix.inputs.home-manager.inputs.nixpkgs.rev'
```

## Use the author's pins

`omniflake.pinned.<name>` evaluates a flake with the inputs in its own lock
file, without substitution:

```console
$ nix run 'github:fzakaria/omniflake#pinned.nh.packages.x86_64-linux.default'
```

## Choose what is substituted

For one flake:

```nix
let
  nh = omniflake.lib.load "nh" { nixpkgs = nixpkgs-stable; };
in
nh.packages.x86_64-linux.default
```

For every flake:

```nix
let
  flakes = omniflake.lib.withOverrides {
    nixpkgs = nixpkgs;
    nixpkgs-stable = nixpkgs-stable;
  };
in
flakes.sops-nix.nixosModules.sops
```

For one copy of everything:

```nix
omniflake.unified.sops-nix.nixosModules.sops
```

Passing `{ }` is the same as `pinned`. See [Unification](./unification.md).

## Name a flake

There are three spellings, and they are the same thunk: a flake reached by
two of them is fetched once.

```nix
omniflake.flakes.home-manager                          # bare
omniflake.flakes."github:nix-community/home-manager"   # qualified
omniflake.github.flakes.nix-community.home-manager     # nested
```

The qualified and nested spellings work for every flake in the index. The
bare one is a name a repository has to earn: it is assigned only when one
repository claims it, or when a `names.txt` line hands it over. Sixty-one
repositories are named `home-manager` and 110 are named `flake`, so most
of the contested names belong to nobody. See
[Adding or removing a flake](./adding-a-flake.md#names).

Reach for the qualified spelling when you want to be sure which repository
you are getting, and the nested one in `nix repl`, where the owner is an
attribute you can complete:

```console
$ nix repl github:fzakaria/omniflake
nix-repl> github.flakes.nix-community.<TAB>
```

All three work under `pinned` and `unified` as well as `flakes`.

## Find a flake

The index is searchable at <https://omniflake.com/>, by name, owner/repo or
description. From the command line:

```console
$ nix eval --json github:fzakaria/omniflake#lib.names | jq -r '.[]' | grep sops
```

`lib.names` lists the bare names only. A flake with no bare name is still
in the index and still reachable by the other two spellings; the site shows
every flake and the attribute paths that reach it.

A flake missing from the index can be added; see
[Adding or removing a flake](./adding-a-flake.md).
