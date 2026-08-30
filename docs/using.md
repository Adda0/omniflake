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

Passing `{ }` is the same as `pinned`. See [Unification](./unification.md).

## Find a flake

The attribute name is the repository name, with the owner appended when two
repositories share one. The index is searchable at
<https://fzakaria.github.io/omniflake/>, or:

```console
$ nix eval --json github:fzakaria/omniflake#lib.names | jq -r '.[]' | grep sops
```

A flake missing from the index can be added; see
[Adding or removing a flake](./adding-a-flake.md).
