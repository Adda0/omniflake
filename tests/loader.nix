# Exercises lib/load.nix on real flakes, which fetches their trees at
# evaluation time. Three shapes: a flake that ships a current lock (nh), one
# whose inputs the default policy leaves alone under `pinned` (sops-nix), and
# one with a nested input whose nixpkgs the default policy has to reach
# (agenix -> home-manager -> nixpkgs).
{ self, system }:
let
  ours = self.inputs.nixpkgs.rev;

  nh = self.flakes.nh;
  sops = self.flakes.sops-nix;
  agenix = self.flakes.agenix;
  pinnedSops = self.pinned.sops-nix;
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
{
  nixpkgs = ours;
  checked = [
    "nh"
    "sops-nix"
    "agenix"
  ];
}
