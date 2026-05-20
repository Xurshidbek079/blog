# Blog — Technical Overview

Personal blog for Xurshid (xurshidr.uz). Flask app serving Markdown content in three languages with a Telegram bot for remote administration.

---

## Stack

| Layer | Technology |
|---|---|
| Web framework | Python / Flask 3.0, Jinja2 templates |
| WSGI server | Gunicorn (2 workers, `127.0.0.1:8000`) |
| Reverse proxy | Nginx → HTTPS via Let's Encrypt (Certbot) |
| Content | Markdown files with YAML frontmatter |
| Data | YAML files (books, projects, tools) |
| Bot | python-telegram-bot 21.6 |
| Hosting | VPS at `64.176.59.59` |
| Domains | `xurshidr.uz`, `xurshidbro.uz`, `xurshid.org` |

Dependencies: `flask`, `markdown`, `pyyaml`, `gunicorn` (see `requirements.txt`). Bot deps in `bot/requirements.txt`.

---

## Directory Layout

```
blog/
├── app.py                        # Flask app — all routes and helpers
├── requirements.txt
├── blog.service                  # systemd: runs gunicorn
├── blog-bot.service              # systemd: runs Telegram bot
├── nginx.conf                    # reverse proxy config
├── bot/
│   ├── bot.py                    # Telegram admin bot (all commands)
│   └── requirements.txt
├── content/
│   ├── blog/                     # Short blog posts (/blog route)
│   ├── posts/                    # Long-form essays (/essays route)
│   ├── poems/                    # Poems (/poems route)
│   ├── drafts/                   # Unpublished content (bot saves here)
│   ├── about.md                  # Static pages (each has .uz.md + .uz_cyr.md)
│   ├── now.md
│   ├── contact.md
│   ├── books.yaml                # Book list (status: reading/done/want)
│   ├── projects.yaml             # Projects list
│   ├── projects.uz_cyr.yaml      # Cyrillic variant
│   └── tools.yaml                # Tools list
├── templates/
│   ├── base.html                 # Layout, nav, inline CSS
│   ├── home.html
│   ├── essays.html               # Reused for /essays, /blog, /poems lists
│   ├── post.html                 # Single post view
│   ├── page.html                 # Generic static page (about/now/contact)
│   ├── books.html
│   ├── projects.html
│   ├── tools.html
│   ├── 404.html
│   ├── feed.xml                  # RSS feed template
│   └── sitemap.xml
└── scripts/
    ├── new.sh                    # Create draft locally: ./scripts/new.sh "Title"
    ├── publish.sh                # Move draft to posts/: ./scripts/publish.sh file.md
    ├── uz_to_cyr.py              # Batch transliterate content/blog/*.md → *.uz_cyr.md
    ├── import_from_telegram.py   # Import posts from Telegram JSON export
    ├── create_stubs.py           # Create stub posts with Telegram links
    └── update-tt.sh              # Updates blogTT.md (called by post-commit hook)
```

---

## Language System

Three languages: `en` (English), `uz` (Uzbek Latin), `uz_cyr` (Uzbek Cyrillic).

**Detection order** (`detect_lang()` in `app.py:134`):
1. Cookie `lang` (set by `/lang/<code>`, persists 1 year)
2. `Accept-Language` header — if starts with `uz`, returns `uz`
3. Default: `en`

**File naming convention** for localised content:
- Base (English): `content/blog/2025-05-20-etibor.md`
- Uzbek Latin: `content/blog/2025-05-20-etibor.uz.md`
- Uzbek Cyrillic: `content/blog/2025-05-20-etibor.uz_cyr.md`

Files ending in `.uz.md` or `.uz_cyr.md` are **language variants** and are excluded from list queries (filtered by `_LANG_VARIANT` regex).

**`localized_post()`** (`app.py:158`): returns the correct language variant, falling back to English. Structural fields (`date`, `slug`, `tags`, `published`) **always come from the base English file** so edits to metadata propagate to all languages automatically.

**UI strings** are in the `TRANSLATIONS` dict (`app.py:16`), injected into every template via `inject_globals()`. Templates access them as `{{ t.key_name }}`.

**`scripts/uz_to_cyr.py`**: batch converts all base `.md` files in `content/blog/` to `.uz_cyr.md` using a transliteration table. Protects code blocks, inline code, and URLs from conversion.

---

## Post Format

All posts use YAML frontmatter:

```markdown
---
title: "Post Title"
date: 2025-05-20
slug: post-slug
published: true
tags: [tag1, tag2]
---

Body content in Markdown.
```

- `slug` overrides the filename-derived slug. If omitted, slug is derived from filename by stripping the `YYYY-MM-DD-` prefix.
- `published: false` hides a post from listings (drafts pattern).
- `tags` is optional; posts can be filtered by tag via `?tag=name` query param.
- Markdown extensions enabled: `fenced_code`, `tables`, `footnotes`. Poems additionally get `nl2br`.

---

## Routes

| Route | Handler | Description |
|---|---|---|
| `/` | `home()` | Shows 5 most recent essays |
| `/blog` | `blog()` | Blog post list (supports `?tag=`) |
| `/blog/<slug>` | `blog_post()` | Single blog post |
| `/essays` | `essays()` | Essay list (supports `?tag=`) |
| `/essays/<slug>` | `post()` | Single essay |
| `/poems` | `poems()` | Poem list |
| `/poems/<slug>` | `poem()` | Single poem |
| `/about` | `about()` | Markdown page |
| `/now` | `now()` | Markdown page |
| `/contact` | `contact()` | Markdown page |
| `/projects` | `projects()` | From `projects.yaml` |
| `/books` | `books()` | From `books.yaml`, split by status |
| `/tools` | `tools()` | From `tools.yaml` |
| `/feed.xml` | `feed()` | RSS feed (essays only) |
| `/sitemap.xml` | `sitemap()` | XML sitemap |
| `/lang/<code>` | `set_lang()` | Sets language cookie, redirects back |

---

## Caching

All file reads are cached with `@lru_cache(maxsize=None)` on these functions:
- `get_posts()`, `get_slug_map()` — essays
- `get_blog_posts()`, `get_blog_slug_map()` — blog posts
- `get_poems()`, `get_poems_slug_map()` — poems
- `_render_md()` — rendered Markdown pages
- `read_yaml()` — YAML data files
- `_lang_title()` — per-file language title lookup

**Cache is invalidated by restarting gunicorn** (`systemctl restart blog`). This is done automatically by the bot after any content change.

---

## Deployment

### systemd Services

**`blog.service`** — Flask/Gunicorn:
```
ExecStart=/usr/bin/python3 -m gunicorn -w 2 -b 127.0.0.1:8000 app:app
WorkingDirectory=/root/blog
User=root
```

**`blog-bot.service`** — Telegram bot:
```
ExecStart=/usr/bin/python3 /root/blog/bot/bot.py
EnvironmentFile=/root/blog/bot.env   ← contains BOT_TOKEN and ADMIN_ID
WorkingDirectory=/root/blog
User=root
```

### Nginx

Nginx listens on port 443 (HTTPS) and proxies to `127.0.0.1:8000`. SSL certificate at `/etc/letsencrypt/live/xurshid.org/` (covers `xurshid.org` and `www.xurshid.org`); `xurshidr.uz` and `www.xurshidr.uz` redirect to HTTPS via the HTTP block. HTTP on port 80 redirects to HTTPS. Static files served directly from `/root/blog/static/` with 30-day cache.

### Content Paths on Server

The server uses `/root/blog/` as the project root (not the dev machine path). Bot hardcodes these:
- Essays: `/root/blog/content/posts/`
- Blog posts: `/root/blog/content/blog/`
- Poems: `/root/blog/content/poems/`
- Drafts: `/root/blog/content/drafts/`

---

## Telegram Bot (`bot/bot.py`)

Admin-only: every handler checks `update.effective_user.id == ADMIN_ID` before acting.

Environment variables (from `bot.env`):
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_ID` — Telegram user ID of the admin

### Commands

| Command | Description |
|---|---|
| `/start` | Shows command list |
| `/newessay` | Conversation: create essay in `content/posts/` |
| `/newpost` | Conversation: create blog post in `content/blog/` |
| `/newpoem` | Conversation: create poem in `content/poems/` |
| `/edit` | Conversation: replace content of existing post |
| `/drafts` | List drafts; pick one to publish to essay/blog/poems |
| `/essays` | List 10 most recent essays |
| `/posts` | List 10 most recent blog posts |
| `/delete` | Delete essay or blog post (and all language variants) |
| `/pages` | Edit static pages (About, Now, Contact) or YAML data files |
| `/restart` | `systemctl restart blog` |
| `/status` | `systemctl status blog` |

### New Post Conversation Flow

State machine: `TITLE → TAGS → CONTENT → ASK_UZ → ASK_CYR → FINAL_CONFIRM`

1. Title (text)
2. Tags — comma-separated slugified tags, or `/skip`
3. Content — full Markdown body
4. Uzbek Latin translation — text or `/skip`
5. Uzbek Cyrillic translation — text or `/skip`
6. Inline keyboard: **Publish now** / **Save as draft** / **Cancel**

Publishing writes files directly to the target directory and calls `systemctl restart blog`. Saving as draft writes to `content/drafts/` without restart.

All language variants (`fname`, `fname.uz.md`, `fname.uz_cyr.md`) are created if provided, with identical frontmatter.

### Pages Conversation

Edits any of: About, Now, Contact (Markdown with language selection) or Projects, Books, Tools (YAML, no language variants). After saving, restarts the blog service.

---

## Scripts

### `scripts/new.sh "Title"`
Creates a dated draft at `content/drafts/YYYY-MM-DD-slug.md` with pre-filled frontmatter. Use on dev machine.

### `scripts/publish.sh path/to/file.md`
Copies the file to `content/posts/`. Optionally commits and pushes to git.

### `scripts/uz_to_cyr.py`
Reads every base `.md` in `content/blog/`, transliterates UZ Latin → Cyrillic, writes `.uz_cyr.md` alongside. Protects URLs, code spans, and fenced code blocks. Run after adding or editing blog posts if you want Cyrillic variants regenerated.

### `scripts/import_from_telegram.py`
One-off import from a Telegram JSON export. Reads `~/Downloads/.../result.json`, filters to `TARGET_IDS`, converts Telegram entity formatting to Markdown, writes to `content/blog/`. Adjust `TARGET_IDS` and `JSON_PATH` before running.

### `scripts/create_stubs.py`
Creates stub posts in `content/blog/` with `published: false` and a link to the Telegram post. Used to pre-populate dates while actual content is being migrated.

---

## Git Hook

`.git/hooks/post-commit` calls `scripts/update-tt.sh` after every commit to keep `blogTT.md` current.

---

## Key Design Decisions

- **No database** — all content is flat Markdown/YAML files. New content requires a service restart to clear the `lru_cache`.
- **No JavaScript** — pure server-rendered HTML, inline CSS in `base.html`. No build step.
- **Single-file app** — all Flask logic lives in `app.py`. Templates extend `base.html`.
- **`essays.html` is reused** for `/essays`, `/blog`, and `/poems` list pages — the route passes `base_url` and `page_title` to differentiate them.
- **Language variants are opt-in** — if a `.uz.md` or `.uz_cyr.md` file doesn't exist, the English base is served instead. No error.
- **Bot restarts the service** on every publish/edit/delete to invalidate the cache. With 2 Gunicorn workers, this causes ~1s downtime.
