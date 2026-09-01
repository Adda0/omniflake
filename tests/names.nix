# Checks that every flake is reachable by its qualified name as well as by
# its attribute name, without fetching any of them: an attribute set is
# built and its keys are asked about, and no value is ever forced.
{ self, ... }:
let
  inherit (builtins)
    all
    attrNames
    filter
    fromJSON
    length
    match
    readFile
    ;

  index = fromJSON (readFile ../index.json);
  names = attrNames index;

  qualified =
    name:
    let
      locked = index.${name}.locked;
    in
    "${locked.type}:${locked.owner}/${locked.repo}";

  # A bare name is a legal Nix attribute name and a qualified one carries a
  # colon, so the two key spaces share no key and can live in one set.
  colonInBareName = filter (name: match ".*:.*" name != null) names;

  # Every flake answers to its qualified name under all three policies.
  missingQualified = filter (
    name:
    !(
      self.flakes ? ${qualified name}
      && self.pinned ? ${qualified name}
      && self.unified ? ${qualified name}
    )
  ) names;

  # Every GitHub flake answers to github.<policy>.<owner>.<repo>.
  githubNames = filter (name: index.${name}.locked.type == "github") names;
  missingNested = filter (
    name:
    let
      locked = index.${name}.locked;
    in
    !(
      (self.github.flakes.${locked.owner} or { }) ? ${locked.repo}
      && (self.github.pinned.${locked.owner} or { }) ? ${locked.repo}
      && (self.github.unified.${locked.owner} or { }) ? ${locked.repo}
    )
  ) githubNames;

  # The forge roots are written out in flake.nix rather than derived from
  # the data, so an index that grows a second forge is a deliberate change
  # and not a root attribute appearing on its own.
  unreachableForge = filter (name: index.${name}.locked.type != "github") names;
in
assert colonInBareName == [ ];
assert missingQualified == [ ];
assert missingNested == [ ];
assert unreachableForge == [ ];
assert all (name: self.flakes ? ${name}) names;
{
  flakes = length names;
  qualifiedNames = length names;
  github = length githubNames;
}
