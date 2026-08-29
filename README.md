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
[Unification](./docs/unification.md) ·
[Adding or removing a flake](./docs/adding-a-flake.md) ·
[Building the index](./docs/building-the-index.md) ·
[Caveats](./docs/caveats.md)

## Status

![check workflow](https://github.com/fzakaria/omniflake/actions/workflows/check.yml/badge.svg?branch=main)
![update workflow](https://github.com/fzakaria/omniflake/actions/workflows/update.yml/badge.svg?branch=main)

<!-- BEGIN index-status -->

- **12 flakes** in the index, from **12,207 in the library tier** (0 could not be pinned, 12,195 not yet pinned)
- 7 ship no usable lock file and use one computed by Nix
- One `follows` line in your flake redirects `nixpkgs` in every one of them
<!-- END index-status -->

## Quickstart

```console
# what is in here
$ nix eval github:fzakaria/omniflake#lib.count

# use one, without adding it as an input
$ nix run 'github:fzakaria/omniflake#flakes.nh.packages.x86_64-linux.default'
```

Adding omniflake costs one small fetch and adds **six nodes** to your lock
file, however many flakes are in the index. A flake is fetched only when you
evaluate something from it:

```console
$ time nix flake lock
real    0m1.5s
```

## Three ways to reach a flake

| attribute                         | `nixpkgs` (and four other foundations) come from     |
| --------------------------------- | ---------------------------------------------------- |
| `omniflake.flakes.<name>`         | you, at every depth — what modules and overlays want |
| `omniflake.pinned.<name>`         | the flake's own lock, exactly as its author tested   |
| `omniflake.lib.load "<name>" {…}` | whatever you pass; `{ }` means the author's pins     |

See [Unification](./docs/unification.md).

## Why not just add the flakes yourself

You can, and for three or four you should. This exists for the case where you
want `disko` today and `lanzaboote` next week without another four lines and
another thing to update — and because a single `follows` here redirects
`nixpkgs` in every one of them at once, at any depth.

See [Caveats](./docs/caveats.md) first. It asks you to trust one repository's
pinning of thousands of others.
