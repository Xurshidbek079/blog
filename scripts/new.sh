#!/bin/bash
# Usage: ./scripts/new.sh "My Essay Title"
# Creates a new draft MD file with frontmatter pre-filled.
set -e

TITLE="$*"
if [ -z "$TITLE" ]; then
    echo "Usage: $0 \"My Essay Title\""
    exit 1
fi

SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//' | sed 's/-$//')
DATE=$(date +%Y-%m-%d)
FILENAME="${DATE}-${SLUG}.md"
DRAFTS_DIR="$(dirname "$0")/../content/drafts"
mkdir -p "$DRAFTS_DIR"
DEST="$DRAFTS_DIR/$FILENAME"

cat > "$DEST" <<EOF
---
title: $TITLE
date: $DATE
slug:
published: true
tags: []
---

Write here.
EOF

echo "✓ Draft created: $DEST"
echo "  Edit, then run: ./scripts/publish.sh $DEST"
