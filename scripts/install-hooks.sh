#!/bin/sh
# Pasang git hook muse-parlay-analyst dari scripts/ ke .git/hooks/.
# Jalankan sekali setelah clone: sh scripts/install-hooks.sh
set -e
REPO_ROOT=$(git rev-parse --show-toplevel)
cp "$REPO_ROOT/scripts/pre-commit" "$REPO_ROOT/.git/hooks/pre-commit"
chmod +x "$REPO_ROOT/.git/hooks/pre-commit"
echo "Hook pre-commit terpasang."
