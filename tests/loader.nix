# Exercises lib/load.nix on real flakes, which fetches their trees at
# evaluation time. Four shapes: a flake that ships a current lock (nh), one
# whose inputs the default policy leaves alone under `pinned` (sops-nix),
# one with a nested input whose nixpkgs the default policy has to reach
# (agenix -> home-manager -> nixpkgs), and one that `unified` has to reach
# past the foundations for (devenv -> cachix -> git-hooks).
{ self, system }:
let
  ours = self.inputs.nixpkgs.rev;

  nh = self.flakes.nh;
  sops = self.flakes.sops-nix;
  agenix = self.flakes.agenix;
  pinnedSops = self.pinned.sops-nix;

  # `unified` overrides on every indexed name, and the flake it substitutes
  # is itself unified: devenv's cachix comes from the index, and that
  # cachix's git-hooks does too, rather than the one cachix locked.
  devenv = self.unified.devenv;
in
# A flake evaluates to the shape Nix gives one.
assert nh._type == "flake";
assert nh ? packages.${system};
# Unification by name reaches a direct input...
assert nh.inputs.nixpkgs.rev == ours;
# ...and a nested one, without a follows line anywhere.
assert agenix.inputs.home-manager.inputs.nixpkgs.rev == ours;
# An input the policy does not name keeps the author's pin.
assert agenix.inputs.darwin.rev != ours;
# A flake evaluates from its own lock...
assert sops ? nixosModules.sops;
# ...and `pinned` leaves even nixpkgs on what that lock says.
assert pinnedSops.inputs.nixpkgs.rev != ours;
# `unified` substitutes a name the foundations do not cover...
assert devenv.inputs.cachix.rev == self.unified.cachix.rev;
# ...and keeps substituting inside what it substituted.
assert devenv.inputs.cachix.inputs.git-hooks.rev == self.unified.git-hooks.rev;
# A foundation still wins over the index entry of the same name, so
# `inputs.omniflake.inputs.nixpkgs.follows` reaches `unified` as well.
assert devenv.inputs.nixpkgs.rev == ours;
{
  nixpkgs = ours;
  checked = [
    "nh"
    "sops-nix"
    "agenix"
    "devenv"
  ];
}
