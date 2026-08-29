# Evaluate one pinned flake from its own lock file, at evaluation time.
#
# This is what Nix does with a lock file (src/libflake/call-flake.nix):
# `builtins.fetchTree` on each node's locked attributes, `import` its
# flake.nix, call `outputs` with the inputs the lock names. Doing that here
# is what lets a flake be reachable without being an input: nothing is
# fetched until an attribute of its result is forced, and the consumer's
# lock file never learns about the flake's transitive graph.
#
# One deviation from call-flake.nix: an edge whose input *name* appears in
# `overrides` gets the override, at any depth. That is unification by
# name, the effect `inputs.x.inputs.nixpkgs.follows = "nixpkgs"` has at
# lock time, applied at evaluation time instead.
{
  # The `locked` attribute set for the flake itself, as `nix flake
  # metadata --json` reports it: enough for fetchTree in pure mode.
  locked,
  # A parsed lock file to use instead of the one in the fetched tree, or
  # null. Supplied when the flake ships no lock or a stale one.
  lock ? null,
  # Attribute set of input name to flake (or source tree) that replaces
  # every input by that name, at every depth.
  overrides ? { },
}:
let
  inherit (builtins)
    fetchTree
    fromJSON
    head
    isList
    mapAttrs
    pathExists
    readFile
    substring
    tail
    ;

  rootSource = fetchTree locked;

  # A flake with no lock file and no inputs still has to evaluate.
  emptyLock = {
    nodes.root = { };
    root = "root";
    version = 7;
  };

  lockFile =
    if lock != null then
      lock
    else if pathExists (rootSource.outPath + "/flake.lock") then
      fromJSON (readFile (rootSource.outPath + "/flake.lock"))
    else
      emptyLock;

  # An input spec is a node name, or a `follows` path from the root node.
  resolveInput =
    inputSpec: if isList inputSpec then getInputByPath lockFile.root inputSpec else inputSpec;

  # Walk an input path such as ["home-manager" "nixpkgs"] from a node to
  # the node it ends at, resolving any follows along the way.
  getInputByPath =
    nodeName: path:
    if path == [ ] then
      nodeName
    else
      getInputByPath (resolveInput lockFile.nodes.${nodeName}.inputs.${head path}) (tail path);

  # An override stands in for a whole node, so it has to match the
  # flakeness of the node it replaces: a `flake = false` edge expects a
  # source tree, not a set of outputs.
  overrideFor =
    inputName: targetNode:
    let
      override = overrides.${inputName};
    in
    if targetNode.flake or true then override else override.sourceInfo or override;

  allNodes = mapAttrs (
    key: node:
    let
      isRoot = key == lockFile.root;

      # A relative `path:` input lives inside its parent's tree.
      isRelative = node.locked.type or null == "path" && substring 0 1 node.locked.path != "/";

      parentNode = allNodes.${getInputByPath lockFile.root node.parent};

      sourceInfo =
        if isRoot then
          rootSource
        else if isRelative then
          parentNode.sourceInfo
        else
          fetchTree (node.info or { } // removeAttrs node.locked [ "dir" ]);

      subdir = node.locked.dir or "";

      # The path before appending the `?dir=` value: a source root, except
      # for a relative `path:` input, which sits under its parent.
      subdirBase =
        if !isRoot && isRelative then
          parentNode.outPath + (if node.locked.path == "" then "" else "/" + node.locked.path)
        else
          sourceInfo.outPath;

      outPath = subdirBase + (if subdir == "" then "" else "/" + subdir);

      flake = import (outPath + "/flake.nix");

      inputs = mapAttrs (
        inputName: inputSpec:
        let
          targetKey = resolveInput inputSpec;
        in
        if overrides ? ${inputName} then
          overrideFor inputName (lockFile.nodes.${targetKey} or { })
        else
          allNodes.${targetKey}.result
      ) (node.inputs or { });

      outputs = flake.outputs (inputs // { self = result; });

      # The same shape Nix gives a flake: outputs, then the source metadata,
      # then the attributes that let a consumer see its inputs.
      result =
        outputs
        // sourceInfo
        // {
          inherit
            outPath
            inputs
            outputs
            sourceInfo
            ;
          _type = "flake";
        };
    in
    {
      result =
        if node.flake or true then
          assert builtins.isFunction flake.outputs;
          result
        else
          sourceInfo // { inherit sourceInfo outPath; };

      inherit outPath sourceInfo;
    }
  ) lockFile.nodes;
in
allNodes.${lockFile.root}.result
