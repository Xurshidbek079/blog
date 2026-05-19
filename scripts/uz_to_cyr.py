#!/usr/bin/env python3
"""Transliterate Uzbek Latin blog posts to Uzbek Cyrillic script.

Creates {stem}.uz_cyr.md alongside each base .md file in content/blog/.
Only the text is converted — URLs, code blocks, slugs, dates are preserved.
"""
import re
import sys
from pathlib import Path

BLOG_DIR = Path(__file__).parent.parent / "content" / "blog"

# ── Transliteration table ─────────────────────────────────────────────────────
# Order matters: process longer sequences before single chars.
MULTI = [
    # o' / g' with various apostrophe forms (all normalised to ' before this)
    ("O'", "Ў"), ("o'", "ў"),
    ("G'", "Ғ"), ("g'", "ғ"),
    # digraphs
    ("SH", "Ш"), ("Sh", "Ш"), ("sh", "ш"),
    ("CH", "Ч"), ("Ch", "Ч"), ("ch", "ч"),
    ("NG", "НГ"), ("Ng", "Нг"), ("ng", "нг"),
    ("YO", "Ё"),  ("Yo", "Ё"),  ("yo", "ё"),
    ("YU", "Ю"),  ("Yu", "Ю"),  ("yu", "ю"),
    ("YA", "Я"),  ("Ya", "Я"),  ("ya", "я"),
]

SINGLE = str.maketrans(
    "AaBbDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvXxYyZz",
    "АаБбДдЕеФфГгҲҳИиЖжКкЛлМмНнОоПпҚқРрСсТтУуВвХхЙйЗз",
)

APOSTROPHES = str.maketrans("ʻʼ‘’`ʼ", "''''''")


def _transliterate_chunk(text: str) -> str:
    """Transliterate a plain-text chunk (no URLs or code inside)."""
    # Normalise all apostrophe variants → plain '
    text = text.translate(APOSTROPHES)
    # Apply multi-char replacements
    for lat, cyr in MULTI:
        text = text.replace(lat, cyr)
    # Apply single-char replacements
    text = text.translate(SINGLE)
    # Remaining plain apostrophes (ba'zi → баъзи) → ъ
    text = text.replace("'", "ъ")
    # Word-initial е/Е → э/Э  (Latin 'e' at word-start = Uzbek Э, not Е)
    text = re.sub(r'\bЕ', 'Э', text)
    text = re.sub(r'\bе', 'э', text)
    return text


# Patterns to protect from transliteration:
#   1. Fenced code blocks  ```...```
#   2. Inline code         `...`
#   3. Markdown link URLs  ](url)
#   4. Angle-bracket URLs  <https://...>
#   5. Bare URLs           https://... or http://...
_PROTECT = re.compile(
    r"(```[\s\S]*?```"          # fenced code
    r"|`[^`]+`"                 # inline code
    r"|\]\([^)]+\)"             # markdown link url part
    r"|<https?://[^>]+>"        # angle-bracket url
    r"|https?://\S+"            # bare url
    r")"
)


def transliterate_body(text: str) -> str:
    parts = _PROTECT.split(text)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:          # protected segment — keep as-is
            out.append(part)
        else:
            out.append(_transliterate_chunk(part))
    return "".join(out)


def transliterate_title(title: str) -> str:
    """Transliterate just the title string (no markdown/URLs inside)."""
    return _transliterate_chunk(title)


def convert_file(src: Path) -> Path:
    raw = src.read_text(encoding="utf-8")

    if raw.startswith("---"):
        _, fm_raw, body = raw.split("---", 2)
    else:
        fm_raw, body = "", raw

    # Transliterate only the title value in frontmatter, keep everything else
    def _tr_title(m):
        quote = m.group(1)  # " or '
        val   = m.group(2)
        return f'title: {quote}{transliterate_title(val)}{quote}'

    fm_out = re.sub(
        r'title:\s*(["\'])(.*?)\1',
        _tr_title,
        fm_raw,
    )
    # Unquoted title fallback
    fm_out = re.sub(
        r'title:\s*(?!["\'])(.+)',
        lambda m: f'title: {transliterate_title(m.group(1))}',
        fm_out,
    )

    body_out = transliterate_body(body)

    stem = src.stem                              # e.g. 2024-03-18-atrof-...
    dest = src.parent / f"{stem}.uz_cyr.md"
    dest.write_text(f"---{fm_out}---{body_out}", encoding="utf-8")
    return dest


def main():
    _LV = re.compile(r'\.(uz|uz_cyr)\.md$')
    sources = sorted(
        [p for p in BLOG_DIR.glob("*.md") if not _LV.search(p.name)]
    )
    if not sources:
        print("No base .md files found in", BLOG_DIR)
        sys.exit(1)

    for src in sources:
        dest = convert_file(src)
        print(f"  {src.name}  →  {dest.name}")

    print(f"\nDone — {len(sources)} files converted.")


if __name__ == "__main__":
    main()
