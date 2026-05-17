#!/bin/bash
# Usage: ./scripts/publish.sh path/to/essay.md
# Copies the file into content/posts/ and optionally pushes to git.
set -e

FILE="$1"
POSTS_DIR="$(dirname "$0")/../content/posts"

if [ -z "$FILE" ]; then
    echo "Usage: $0 <file.md>"
    echo ""
    echo "File must have frontmatter:"
    echo "  ---"
    echo "  title: My Essay"
    echo "  date: $(date +%Y-%m-%d)"
    echo "  published: true"
    echo "  ---"
    exit 1
fi

if [ ! -f "$FILE" ]; then
    echo "Error: file not found: $FILE"
    exit 1
fi

DEST="$POSTS_DIR/$(basename "$FILE")"
cp "$FILE" "$DEST"
echo "✓ Published: $DEST"

# Optional: auto-push to git
if git -C "$(dirname "$0")/.." rev-parse --git-dir > /dev/null 2>&1; then
    read -p "Push to git? [y/N] " yn
    if [[ "$yn" == "y" || "$yn" == "Y" ]]; then
        cd "$(dirname "$0")/.."
        git add "content/posts/$(basename "$FILE")"
        git commit -m "post: $(basename "$FILE" .md)"
        git push
        echo "✓ Pushed to GitHub"
    fi
fi
