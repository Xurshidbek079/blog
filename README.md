# blog

Minimal personal blog. Flask + Markdown files. No database, no admin panel.

## Stack

- [Flask](https://flask.palletsprojects.com) — web framework
- [Python-Markdown](https://python-markdown.github.io) — renders `.md` files
- [PyYAML](https://pyyaml.org) — reads `.yaml` data files
- [Gunicorn](https://gunicorn.org) — production server
- Nginx — reverse proxy

## Writing

**New post:**
```bash
./scripts/new.sh "My Essay Title"
# Opens a draft at content/drafts/YYYY-MM-DD-my-essay-title.md
# Edit it, then:
./scripts/publish.sh content/drafts/YYYY-MM-DD-my-essay-title.md
```

**Publish existing `.md` directly:**
```bash
./scripts/publish.sh path/to/essay.md
```

The script copies it to `content/posts/` and offers to push to GitHub.

**Post frontmatter format:**
```yaml
---
title: My Essay
date: 2025-01-15
published: true   # set false to hide without deleting
---

Content in Markdown here.
```

## Content files

| File | What to edit |
|---|---|
| `content/posts/*.md` | Blog essays |
| `content/about.md` | About page |
| `content/now.md` | Now page |
| `content/projects.yaml` | Projects list |
| `content/books.yaml` | Books list |
| `content/tools.yaml` | Tools list |

## Local setup

```bash
pip3 install -r requirements.txt
flask --app app run
```

## Deploy (server)

```bash
git clone https://github.com/Xurshidbek079/blog /root/blog
cd /root/blog
pip3 install -r requirements.txt
cp blog.service /etc/systemd/system/
systemctl enable --now blog
cp nginx.conf /etc/nginx/sites-available/blog
ln -s /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## Posting from server

```bash
cd /root/blog
./scripts/new.sh "My New Essay"
# edit the file
./scripts/publish.sh content/drafts/...md
```
