# omniflake

> Please read this [blog post](https://fzakaria.com/2026/08/28/one-flake-to-rule-them-all) for context.

Thousands of Nix flakes behind **one input**. No `url` and `follows` block per
dependency; reach in for what you need and pay nothing for the rest.

```nix
{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.omniflake.url = "github:fzakaria/omniflake";
  inputs.omniflake.inputs.nixpkgs.follows = "nixpkgs";

  outputs = { self, nixpkgs, omniflake, ... }: {
    nixosConfigurations.host = nixpkgs.lib.nixosSystem {
      modules = [
        omniflake.flakes.home-manager.nixosModules.home-manager
        omniflake.flakes.disko.nixosModules.disko
        omniflake.flakes.sops-nix.nixosModules.sops
      ];
    };
  };
}
```

**Documentation:** [How it works](./docs/how-it-works.md) ·
[Adding a flake](./docs/adding-a-flake.md) ·
[Building the index](./docs/building-the-index.md) ·
[Caveats](./docs/caveats.md)

## Status

<!-- BEGIN index-status -->
- **1,574 flakes** in the library tier, from **2,188 resolved** of **2,461 candidates**
- One `follows` line in your flake redirects every subflake onto your nixpkgs
<!-- END index-status -->

## Quickstart

```console
# what is in here
$ nix eval --raw github:fzakaria/omniflake#lib.count

# use one, without adding it as an input
$ nix run 'github:fzakaria/omniflake#flakes.nh.packages.x86_64-linux.default'
```

Adding omniflake costs one small fetch. Its thousands of inputs are *pins*, not
downloads — a subflake is fetched only if you evaluate something from it.

```console
$ time nix flake lock
real    0m1.53s
```

## Why not just add the flakes yourself

You can, and for three or four you should. This exists for the case where you
want `disko` today and `lanzaboote` next week without another four lines and
another thing to update — and because a single `follows` here collapses
duplicate nixpkgs across everything at once.

See [Caveats](./docs/caveats.md) first. It asks you to trust one repository's
pinning of thousands of others.
