#!/usr/bin/env bash
set -euo pipefail
DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DOCS_DIR/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
rm -rf "$DOCS_DIR/_build" "$DOCS_DIR/en/api" "$DOCS_DIR/ja/api"
mkdir -p "$DOCS_DIR/_build/html" "$DOCS_DIR/en/api" "$DOCS_DIR/ja/api"
for lang in en ja; do
  sphinx-apidoc -f -o "$DOCS_DIR/$lang/api" "$ROOT_DIR/src/powder_level_monitor"
  sphinx-build -b html -c "$DOCS_DIR" -D language="$lang" "$DOCS_DIR/$lang" "$DOCS_DIR/_build/html/$lang"
done
cp -R "$DOCS_DIR/_build/html/en/." "$DOCS_DIR/_build/html/"
touch "$DOCS_DIR/_build/html/.nojekyll"
