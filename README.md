# blog

Personal blog built with Flask and Markdown files. No database, no admin panel, no JavaScript.

## How it works

All content lives as plain files on disk. Flask reads them at startup, renders them into HTML via Jinja2 templates, and caches everything in memory. A restart clears the cache and picks up any changes.

```
Internet → Nginx → Gunicorn → Flask (app.py)
```

Posts are Markdown files in `content/posts/`. Pages like About, Now, and Contact are also Markdown. Projects, Books, and Tools are YAML files. Nothing else.

## Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | Flask 3.0.3 |
| Markdown renderer | Python-Markdown 3.6 |
| Data files | PyYAML 6.0.2 |
| Production server | Gunicorn 22.0.0 |
| Reverse proxy | Nginx |
| JavaScript | None |
| Database | None |

## Content structure

| File | Page |
|---|---|
| `content/posts/YYYY-MM-DD-slug.md` | Essays |
| `content/about.md` | About |
| `content/now.md` | Now |
| `content/contact.md` | Contact |
| `content/projects.yaml` | Projects |
| `content/books.yaml` | Books |
| `content/tools.yaml` | Tools |

### Post format

```yaml
---
title: My Essay
date: 2025-01-15
slug: my-essay
published: true
tags: [python, systems]
---

Content in Markdown here.
```

`slug` is optional — if omitted, it's derived from the filename with the date prefix stripped. Setting `published: false` hides the post without deleting the file.

## Philosophy

**No database.** Content is Markdown and YAML files. They are readable without any software, portable to any host, and trivially backed up with git.

**No admin panel.** Posts are written in a text editor. The site is managed through a Telegram bot that can create, publish, and delete posts, and edit any page — without touching a terminal.

**No JavaScript.** The server renders complete HTML. The browser has nothing to execute.

**No secrets.** No API keys, no environment variables, no `.env` file needed to run the site.

**Self-hosted.** Runs on a VPS with root access. No dependency on any platform. The entire site can be moved to a new server in under an hour.

**Two languages.** The site UI is available in English and Uzbek Latin. Language is detected from the browser's `Accept-Language` header and can be switched with a toggle in the nav bar. Post content is never translated.
