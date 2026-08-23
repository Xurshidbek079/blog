#!/usr/bin/env python3
"""Import posts from Telegram JSON export into content/blog/."""
import json
import re
from pathlib import Path
from datetime import datetime

JSON_PATH = Path.home() / "Downloads/Telegram Desktop/ChatExport_2026-05-19/result.json"
BLOG_DIR  = Path(__file__).parent.parent / "content" / "blog"

# Message IDs to import (from the user's list)
TARGET_IDS = {6, 10, 11, 12, 13, 15, 16, 17, 19, 20, 23, 25, 28, 30,
              31, 32, 34, 36, 37, 40, 41, 42, 43, 44, 45, 46, 49, 50, 55}


def entities_to_markdown(text_field) -> str:
    """Convert Telegram text field (str or list of entities) to Markdown."""
    if isinstance(text_field, str):
        return text_field

    parts = []
    for item in text_field:
        if isinstance(item, str):
            parts.append(item)
            continue
        t    = item.get("type", "plain")
        text = item.get("text", "")
        href = item.get("href", "")
        if t == "plain":
            parts.append(text)
        elif t == "bold":
            clean = text.strip()
            parts.append(f"**{clean}**" if clean else text)
        elif t == "italic":
            parts.append(f"*{text}*")
        elif t == "underline":
            parts.append(text)          # no MD underline, keep plain
        elif t == "strikethrough":
            parts.append(f"~~{text}~~")
        elif t == "code":
            parts.append(f"`{text}`")
        elif t == "pre":
            lang = item.get("language", "")
            parts.append(f"```{lang}\n{text}\n```")
        elif t == "text_link":
            parts.append(f"[{text}]({href})")
        elif t == "link":
            parts.append(f"<{text}>")
        elif t in ("mention", "hashtag", "cashtag", "bot_command",
                   "email", "phone_number", "mention_name"):
            parts.append(text)
        elif t == "blockquote":
            quoted = "\n".join(f"> {line}" for line in text.splitlines())
            parts.append(quoted)
        else:
            parts.append(text)
    return "".join(parts)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"['ʻʼ''`!?]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def extract_title(md_body: str, msg_id: int) -> str:
    """Extract title from first bold span, or first non-empty line."""
    m = re.match(r"\*\*(.+?)\*\*", md_body.lstrip())
    if m:
        return m.group(1).strip().rstrip(".")
    # Fall back: first non-empty line, strip any stray markdown markers
    for line in md_body.splitlines():
        line = re.sub(r"^\*+|^\#+", "", line).strip()
        if line:
            return line[:80]
    return f"Post {msg_id}"


def remove_existing_stubs(slug: str):
    """Remove previously created stub files that match this slug."""
    for f in BLOG_DIR.glob(f"*-{slug}.md"):
        f.unlink()
        print(f"  Removed stub: {f.name}")


def main():
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    messages = {m["id"]: m for m in data["messages"] if m.get("type") == "message"}

    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    created = []

    for msg_id in sorted(TARGET_IDS):
        msg = messages.get(msg_id)
        if not msg:
            print(f"  WARNING: message ID {msg_id} not found in export")
            continue

        md_body = entities_to_markdown(msg.get("text", ""))
        if not md_body.strip():
            print(f"  SKIP: message {msg_id} has no text")
            continue

        date_str = msg["date"][:10]           # "2024-03-18"
        title    = extract_title(md_body, msg_id)
        slug     = slugify(title)
        fname    = f"{date_str}-{slug}.md"

        remove_existing_stubs(slug)

        file_content = (
            f'---\n'
            f'title: "{title}"\n'
            f'date: {date_str}\n'
            f'slug: {slug}\n'
            f'published: true\n'
            f'tags: []\n'
            f'---\n\n'
            f'{md_body.strip()}\n'
        )
        (BLOG_DIR / fname).write_text(file_content, encoding="utf-8")
        created.append(fname)
        print(f"  Created: {fname}")

    print(f"\nDone — {len(created)}/{len(TARGET_IDS)} posts imported.")


if __name__ == "__main__":
    main()
