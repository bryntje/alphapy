#!/bin/bash
# Run this from the alphapy repo root to push docs to innersync-tech/docs
# Usage: bash .docs-setup/setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMPDIR=$(mktemp -d)

echo "Cloning innersync-tech/docs..."
git clone https://github.com/innersync-tech/docs.git "$TMPDIR/docs"

echo "Copying files..."
rsync -av "$SCRIPT_DIR/" "$TMPDIR/docs/" --exclude=setup.sh

cd "$TMPDIR/docs"
git add .
git commit -m "chore: initial docs structure migrated from bryntje/alphapy"
git push origin main

echo ""
echo "Done! Cleanup: rm -rf $TMPDIR"
