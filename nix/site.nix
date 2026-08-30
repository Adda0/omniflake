# The deployable site: the static files from site/, the rendered docs, and
# site-data.json built from the committed index and databases.
#
# The data is built here rather than fetched from raw.githubusercontent.com
# at page load so that the page and the index it describes always deploy
# together.
{ pkgs, self }:
let
  # The commit stamped into the footer. From a clean checkout self.rev names
  # exactly the tree the data came from; a dirty tree gets dirtyRev; anything
  # else keeps the placeholder and the footer line stays hidden.
  commit = self.rev or self.dirtyRev or "__COMMIT__";

  docs = import ./docs.nix { inherit pkgs; };

  data = pkgs.runCommand "omniflake-site-data" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    mkdir -p $out
    python3 ${../tools/build-site-data.py} \
      --index ${../index.json} \
      --resolved ${../resolved.jsonl} \
      --failures ${../failures.jsonl} \
      --blocklist ${../blocklist.txt} \
      --locks ${../locks} \
      --out $out/site-data.json
  '';
in
pkgs.runCommand "omniflake-site" { } ''
  mkdir -p $out/docs
  cp -r ${../site}/* $out/
  cp ${data}/site-data.json $out/
  cp -r ${docs}/* $out/docs/
  chmod -R u+w $out

  substituteInPlace $out/js/app.js --replace-quiet "__COMMIT__" "${commit}"
  substituteInPlace $out/js/app.js --replace-fail "__STORE_PATH__" "$out"
  for f in $out/docs/*.html; do
    substituteInPlace "$f" --replace-quiet "__COMMIT__" "${commit}"
    substituteInPlace "$f" --replace-fail "__STORE_PATH__" "$out"
  done

  # Content-hash the module directory after the substitutions, so the HTML
  # and the script it loads can never be a mismatched pair across deploys.
  hash=$(find $out/js -type f -name '*.js' | LC_ALL=C sort |
    xargs sha256sum | sha256sum | cut -c1-12)
  mv $out/js "$out/js.$hash"
  substituteInPlace $out/index.html --replace-fail "./js/app.js" "./js.$hash/app.js"
''
