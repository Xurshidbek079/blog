#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

BOT_TOKEN   = os.environ["BOT_TOKEN"]
ADMIN_ID    = int(os.environ["ADMIN_ID"])
BLOG_DIR    = Path("/root/blog")
POSTS_DIR   = BLOG_DIR / "content/posts"     # listed blog posts  → /blog/<slug>
ESSAYS_DIR  = BLOG_DIR / "content/essays"    # unlisted essays    → /<slug>
DRAFTS_DIR  = BLOG_DIR / "content/drafts"
CONTENT_DIR = BLOG_DIR / "content"
BOOKS_DIR   = BLOG_DIR / "content/books"     # one file per book → /books/<slug>
IMAGES_DIR  = BLOG_DIR / "static/img"
SITE_URL    = "https://xurshid.org"

# Covers go through the same normaliser the web panel uses: proven to be an
# image, EXIF stripped, downscaled. app.py lives one directory up.
sys.path.insert(0, str(BLOG_DIR))
from imagestore import save_image_bytes  # noqa: E402

# Root slugs an essay may never take — keep in sync with _RESERVED_SLUGS in app.py.
RESERVED_SLUGS = {
    "blog", "about", "now", "contact", "projects", "tools", "books",
    "feed.xml", "sitemap.xml", "static", "robots.txt", "favicon.ico", "admin",
}

# ── Conversation states ────────────────────────────────────────────────────────
(TITLE, TAGS, CONTENT, ASK_SUMMARY, ASK_SERIES, FINAL_CONFIRM) = range(6)
(PAGE_PICK, PAGE_CONTENT) = range(6, 8)
(EDIT_PICK, EDIT_CONTENT) = range(8, 10)
(BOOK_TITLE, BOOK_AUTHOR, BOOK_COVER, BOOK_SUMMARY,
 BOOK_NOTES, BOOK_CONFIRM) = range(10, 16)

PAGES = {
    "About":    "about.md",
    "Now":      "now.md",
    "Contact":  "contact.md",
    "Projects": "projects.yaml",
    "Tools":    "tools.yaml",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def shell(cmd: str) -> tuple[int, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def base_posts(directory: Path):
    return sorted(directory.glob("*.md"), reverse=True)


def is_essay(ctx) -> bool:
    return ctx.user_data.get("kind") == "essay"


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "Blog admin\n\n"
        "BLOG POSTS (listed at /blog)\n"
        "/newpost — write a new post\n"
        "/posts — recent posts\n"
        "/edit — edit a post\n"
        "/drafts — list & publish drafts\n"
        "/delete — delete a post\n\n"
        "ESSAYS (unlisted, live at xurshid.org/<slug>)\n"
        "/newessay — write a new essay\n"
        "/essays — list essays + their links\n"
        "/editessay — edit an essay\n"
        "/delessay — delete an essay\n\n"
        "BOOKS (listed at /books)\n"
        "/newbook — add a book\n"
        "/books — list books + their links\n"
        "/editbook — edit a book\n"
        "/delbook — delete a book\n\n"
        "SITE\n"
        "/pages — edit pages (About, Now, Contact, Projects, Tools)\n"
        "/restart — restart blog service\n"
        "/status — service status"
    )


# ── /newessay conversation ────────────────────────────────────────────────────

async def newpost_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    ctx.user_data["kind"] = "post"
    await update.message.reply_text("Post title:")
    return TITLE


async def newessay_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    ctx.user_data["kind"] = "essay"
    await update.message.reply_text(
        "Essay title:\n\n"
        "(unlisted — it will live at xurshid.org/<slug> and appear in no list, "
        "feed, or sitemap)"
    )
    return TITLE


async def got_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    slug  = slugify(title)
    if is_essay(ctx):
        if not slug:
            await update.message.reply_text(
                "That title has no usable letters or digits for a URL. Try another:"
            )
            return TITLE
        if slug in RESERVED_SLUGS:
            await update.message.reply_text(
                f"“/{slug}” is already a page on the site. Pick a different title:"
            )
            return TITLE
        if (ESSAYS_DIR / f"{slug}.md").exists() or any(
            p.stem.endswith(f"-{slug}") for p in base_posts(ESSAYS_DIR)
        ):
            await update.message.reply_text(
                f"An essay already lives at /{slug}. Pick a different title:"
            )
            return TITLE
    ctx.user_data["title"] = title
    await update.message.reply_text("Tags (comma-separated) or /skip:")
    return TAGS


async def got_tags(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    ctx.user_data["tags"] = [slugify(t) for t in raw.split(",") if t.strip()]
    await update.message.reply_text("Content (Markdown):")
    return CONTENT


async def skip_tags(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["tags"] = []
    await update.message.reply_text("Content (Markdown):")
    return CONTENT


async def got_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["content"] = update.message.text
    await update.message.reply_text("Summary (1–2 sentences for link previews) or /skip:")
    return ASK_SUMMARY


async def got_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["summary"] = update.message.text.strip()
    await update.message.reply_text("Series name (for multi-part posts) or /skip:")
    return ASK_SERIES


async def skip_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["summary"] = None
    await update.message.reply_text("Series name (for multi-part posts) or /skip:")
    return ASK_SERIES


async def got_series(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["series"] = update.message.text.strip()
    return await _show_final_confirm(update.message, ctx)


async def skip_series(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["series"] = None
    return await _show_final_confirm(update.message, ctx)


async def _show_final_confirm(message, ctx):
    title   = ctx.user_data["title"]
    tags    = ctx.user_data["tags"]
    summary = (ctx.user_data.get("summary") or "—")[:100]
    series  = ctx.user_data.get("series") or "—"
    essay   = is_essay(ctx)
    where   = f"{SITE_URL}/{slugify(title)}" if essay else f"/blog/{slugify(title)}"
    info = (f"*{title}*\nTags: {', '.join(tags) or 'none'}"
            f"\nSummary: {summary}\nSeries: {series}"
            f"\n\n{'Essay (unlisted)' if essay else 'Blog post'} → `{where}`")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Publish now", callback_data="new:publish"),
        InlineKeyboardButton(
            "Save unpublished" if essay else "Save as draft", callback_data="new:draft"
        ),
        InlineKeyboardButton("Cancel", callback_data="new:cancel"),
    ]])
    await message.reply_text(info, parse_mode="Markdown", reply_markup=kb)
    return FINAL_CONFIRM


async def new_final(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]
    if action == "cancel":
        await q.edit_message_text("Cancelled.")
        return ConversationHandler.END

    title    = ctx.user_data["title"]
    tags     = ctx.user_data["tags"]
    slug     = slugify(title)
    date_str = datetime.now().strftime("%Y-%m-%d")
    fname    = f"{date_str}-{slug}.md"
    tags_yaml = "[" + ", ".join(tags) + "]" if tags else "[]"
    summary  = ctx.user_data.get("summary")
    series   = ctx.user_data.get("series")

    essay = is_essay(ctx)
    # An essay has no list to be left out of, so "unpublished" is a frontmatter flag
    # that makes the route 404 — it stays in content/essays/ either way.
    published = "false" if (essay and action == "draft") else "true"

    fm = (f"---\ntitle: {title}\ndate: {date_str}\nslug: {slug}\n"
          f"published: {published}\ntags: {tags_yaml}\n")
    if summary:
        fm += f'summary: "{summary}"\n'
    if series:
        fm += f'series: "{series}"\n'
    fm += f"---\n\n{ctx.user_data['content']}"

    if essay:
        target = ESSAYS_DIR
    else:
        target = POSTS_DIR if action == "publish" else DRAFTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    (target / fname).write_text(fm, encoding="utf-8")

    if action == "publish":
        shell("systemctl restart blog")
        if essay:
            await q.edit_message_text(
                f"Published ✓\n{SITE_URL}/{slug}\n\nUnlisted — only people with this link can reach it."
            )
        else:
            await q.edit_message_text(f"Published ✓\n{SITE_URL}/blog/{slug}")
    elif essay:
        await q.edit_message_text(
            f"Saved unpublished ✓ {fname}\n\n{SITE_URL}/{slug} will 404 until you "
            f"publish it with /editessay."
        )
    else:
        await q.edit_message_text(f"Draft saved: {fname}")
    return ConversationHandler.END


async def new_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── /newbook conversation ─────────────────────────────────────────────────────

def yaml_str(value: str) -> str:
    """Quote a value for single-line YAML without letting it break out."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def book_slugs() -> set[str]:
    """Every slug already taken by a book."""
    taken = set()
    for p in base_posts(BOOKS_DIR):
        head = p.read_text(encoding="utf-8")[:400]
        m = re.search(r"^slug:\s*(\S+)", head, re.M)
        taken.add(m.group(1).strip("\"'") if m else re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem))
    return taken


async def newbook_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    ctx.user_data.clear()
    ctx.user_data["kind"] = "book"
    await update.message.reply_text("Book title:")
    return BOOK_TITLE


async def book_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    slug = slugify(title)
    if not slug:
        await update.message.reply_text(
            "That title has no usable letters or digits for a URL. Try another:"
        )
        return BOOK_TITLE
    if slug in book_slugs():
        await update.message.reply_text(
            f"A book already lives at /books/{slug}. Pick a different title:"
        )
        return BOOK_TITLE
    ctx.user_data["title"] = title
    await update.message.reply_text("Author (or /skip):")
    return BOOK_AUTHOR


async def book_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["author"] = update.message.text.strip()
    return await _ask_cover(update)


async def skip_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["author"] = ""
    return await _ask_cover(update)


async def _ask_cover(update: Update):
    await update.message.reply_text(
        "Send the cover photo (or /skip).\n\n"
        "Either a normal photo or a file — it gets resized and stripped of metadata "
        "either way."
    )
    return BOOK_COVER


async def book_cover(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        file_id, hint = msg.photo[-1].file_id, ctx.user_data["title"]
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        file_id, hint = msg.document.file_id, msg.document.file_name or ctx.user_data["title"]
    else:
        await msg.reply_text("That is not an image. Send a photo, or /skip:")
        return BOOK_COVER

    tg_file = await ctx.bot.get_file(file_id)
    raw = bytes(await tg_file.download_as_bytearray())
    url = save_image_bytes(raw, hint, IMAGES_DIR)
    if url is None:
        await msg.reply_text("Could not read that as an image. Try another, or /skip:")
        return BOOK_COVER
    ctx.user_data["cover"] = url
    await msg.reply_text(f"Cover saved ✓ {url}\n\nShort summary for the /books list (or /skip):")
    return BOOK_SUMMARY


async def skip_cover(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["cover"] = ""
    await update.message.reply_text("Short summary for the /books list (or /skip):")
    return BOOK_SUMMARY


async def book_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["summary"] = update.message.text.strip()
    return await _ask_notes(update)


async def skip_summary_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["summary"] = ""
    return await _ask_notes(update)


async def _ask_notes(update: Update):
    await update.message.reply_text(
        "Now the notes — your thoughts, highlights, anything.\n\n"
        "Plain text is fine. Markdown works too, so [text](https://url) becomes a link."
    )
    return BOOK_NOTES


async def book_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["notes"] = update.message.text
    d = ctx.user_data
    info = (f"*{d['title']}*\n"
            f"Author: {d.get('author') or '—'}\n"
            f"Cover: {'yes' if d.get('cover') else 'none'}\n"
            f"Summary: {(d.get('summary') or '—')[:100]}\n\n"
            f"→ `{SITE_URL}/books/{slugify(d['title'])}`")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Publish now",      callback_data="book:publish"),
        InlineKeyboardButton("Save unpublished", callback_data="book:draft"),
        InlineKeyboardButton("Cancel",           callback_data="book:cancel"),
    ]])
    await update.message.reply_text(info, parse_mode="Markdown", reply_markup=kb)
    return BOOK_CONFIRM


async def book_final(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":")[1]
    if action == "cancel":
        await q.edit_message_text("Cancelled.")
        return ConversationHandler.END

    d = ctx.user_data
    slug = slugify(d["title"])
    date_str = datetime.now().strftime("%Y-%m-%d")
    fname = f"{date_str}-{slug}.md"
    published = "true" if action == "publish" else "false"

    fm = (f"---\ntitle: {yaml_str(d['title'])}\ndate: {date_str}\nslug: {slug}\n"
          f"published: {published}\ntags: []\n")
    for field in ("author", "cover", "summary"):
        if d.get(field):
            fm += f"{field}: {yaml_str(d[field])}\n"
    fm += f"---\n\n{d['notes']}\n"

    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    (BOOKS_DIR / fname).write_text(fm, encoding="utf-8")
    shell("systemctl restart blog")

    if action == "publish":
        await q.edit_message_text(f"Published ✓\n{SITE_URL}/books/{slug}")
    else:
        await q.edit_message_text(
            f"Saved unpublished ✓ {fname}\n\n{SITE_URL}/books/{slug} will 404 until you "
            f"publish it with /editbook."
        )
    return ConversationHandler.END


async def book_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── /books, /editbook, /delbook ───────────────────────────────────────────────

def _book_line(path: Path) -> str:
    head = path.read_text(encoding="utf-8")[:600]
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    m = re.search(r"^slug:\s*(\S+)", head, re.M)
    if m:
        slug = m.group(1).strip("\"'")
    t = re.search(r'^title:\s*"?(.+?)"?\s*$', head, re.M)
    title = t.group(1) if t else slug
    state = "unpublished" if re.search(r"^published:\s*false", head, re.M) else "live"
    return f"{title} — {SITE_URL}/books/{slug} ({state})"


async def cmd_books(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    files = base_posts(BOOKS_DIR)
    if not files:
        await update.message.reply_text("No books yet. Add one with /newbook.")
        return
    await update.message.reply_text(
        f"Books ({len(files)}):\n" + "\n".join(_book_line(f) for f in files),
        disable_web_page_preview=True,
    )


async def cmd_editbook(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _edit_menu(update, ctx, BOOKS_DIR, "book")


async def cmd_delbook(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _delete_menu(update, ctx, BOOKS_DIR, "book")


# ── /drafts ───────────────────────────────────────────────────────────────────

async def cmd_drafts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    files = base_posts(DRAFTS_DIR)
    if not files:
        await update.message.reply_text("No drafts.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f.name, callback_data=f"draft:{f.name}")]
        for f in files
    ])
    await update.message.reply_text("Drafts:", reply_markup=kb)


async def draft_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    fname = q.data.split(":", 1)[1]
    path  = DRAFTS_DIR / fname
    if not path.exists():
        await q.edit_message_text("Draft not found.")
        return
    preview = path.read_text(encoding="utf-8")[:500]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Publish", callback_data=f"dpub:{fname}"),
        InlineKeyboardButton("Cancel",  callback_data="dpub:no"),
    ]])
    await q.edit_message_text(
        f"`{fname}`\n\n{preview}\n\nPublish to /blog?", parse_mode="Markdown", reply_markup=kb
    )


async def draft_publish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    if q.data == "dpub:no":
        await q.edit_message_text("Cancelled.")
        return
    fname = q.data.split(":", 1)[1]
    src = DRAFTS_DIR / fname
    if not src.exists():
        await q.edit_message_text("Draft not found.")
        return
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    (POSTS_DIR / fname).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    shell("systemctl restart blog")
    await q.edit_message_text(f"Published ✓\n{fname}")


# ── /posts and /essays ────────────────────────────────────────────────────────

async def cmd_posts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    files = base_posts(POSTS_DIR)[:10]
    if not files:
        await update.message.reply_text("No posts yet.")
        return
    await update.message.reply_text("Recent posts:\n" + "\n".join(f.stem for f in files))


def _essay_line(path: Path) -> str:
    """One '<url> — published|unpublished' line for an essay file."""
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    head = path.read_text(encoding="utf-8")[:400]
    m = re.search(r"^slug:\s*(\S+)", head, re.M)
    if m:
        slug = m.group(1).strip('"\'')
    state = "unpublished" if re.search(r"^published:\s*false", head, re.M) else "live"
    return f"{SITE_URL}/{slug} — {state}"


async def cmd_essays(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    files = base_posts(ESSAYS_DIR)
    if not files:
        await update.message.reply_text("No essays yet. Write one with /newessay.")
        return
    await update.message.reply_text(
        "Essays (unlisted):\n" + "\n".join(_essay_line(f) for f in files),
        disable_web_page_preview=True,
    )


# ── /delete and /delessay ─────────────────────────────────────────────────────

async def _delete_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE, directory: Path, label: str):
    if not is_admin(update):
        return
    files = base_posts(directory)
    if not files:
        await update.message.reply_text(f"No {label}s to delete.")
        return
    ctx.user_data["del_dir"] = str(directory)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f.name, callback_data=f"del:{f.name}")]
        for f in files
    ])
    await update.message.reply_text(f"Select {label} to delete:", reply_markup=kb)


async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _delete_menu(update, ctx, POSTS_DIR, "post")


async def cmd_delessay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _delete_menu(update, ctx, ESSAYS_DIR, "essay")


async def delete_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    directory = Path(ctx.user_data.get("del_dir", POSTS_DIR))
    fname = q.data.split(":", 1)[1]
    if not (directory / fname).exists():
        await q.edit_message_text("Not found.")
        return
    ctx.user_data["delete"] = fname
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, delete", callback_data="delconf:yes"),
        InlineKeyboardButton("Cancel",      callback_data="delconf:no"),
    ]])
    await q.edit_message_text(f"Delete *{fname}*?", parse_mode="Markdown", reply_markup=kb)


async def delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    if q.data == "delconf:no":
        await q.edit_message_text("Cancelled.")
        return
    fname = ctx.user_data.get("delete")
    if not fname:
        await q.edit_message_text("Nothing selected.")
        return
    p = Path(ctx.user_data.get("del_dir", POSTS_DIR)) / fname
    if p.exists():
        p.unlink()
    shell("systemctl restart blog")
    await q.edit_message_text(f"Deleted ✓ {fname}")


# ── /pages conversation ───────────────────────────────────────────────────────

async def cmd_pages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"page:{fname}")]
        for label, fname in PAGES.items()
    ])
    await update.message.reply_text("Which page?", reply_markup=kb)
    return PAGE_PICK


async def page_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    fname = q.data.split(":", 1)[1]
    ctx.user_data["edit_page"] = fname
    path = CONTENT_DIR / fname
    current = path.read_text(encoding="utf-8") if path.exists() else "(empty)"
    if len(current) > 3000:
        current = current[:3000] + "\n…(truncated)"
    kind = "YAML" if fname.endswith(".yaml") else "Markdown"
    await q.edit_message_text(
        f"*{fname}* (current):\n\n```\n{current}\n```\n\nSend new {kind} content, or /cancel:",
        parse_mode="Markdown",
    )
    return PAGE_CONTENT


async def page_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fname = ctx.user_data.get("edit_page", "")
    (CONTENT_DIR / fname).write_text(update.message.text, encoding="utf-8")
    shell("systemctl restart blog")
    await update.message.reply_text(f"Saved ✓ {fname}")
    return ConversationHandler.END


async def pages_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── /edit conversation ────────────────────────────────────────────────────────

async def _edit_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE, directory: Path, label: str):
    if not is_admin(update):
        return ConversationHandler.END
    files = base_posts(directory)[:10]
    if not files:
        await update.message.reply_text(f"No {label}s found.")
        return ConversationHandler.END
    ctx.user_data["edit_dir"] = str(directory)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f.stem, callback_data=f"edit:{f.name}")]
        for f in files
    ])
    await update.message.reply_text(f"Select {label} to edit:", reply_markup=kb)
    return EDIT_PICK


async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _edit_menu(update, ctx, POSTS_DIR, "post")


async def cmd_editessay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _edit_menu(update, ctx, ESSAYS_DIR, "essay")


async def edit_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    fname = q.data.split(":", 1)[1]
    path = Path(ctx.user_data.get("edit_dir", POSTS_DIR)) / fname
    if not path.exists():
        await q.edit_message_text("File not found.")
        return ConversationHandler.END
    ctx.user_data["edit_post_path"] = str(path)
    current = path.read_text(encoding="utf-8")
    if len(current) > 3500:
        current = current[:3500] + "\n…(truncated)"
    await q.edit_message_text(
        f"*{fname}* (current):\n\n```\n{current}\n```\n\n"
        "Send the full new content (with frontmatter) or /cancel:",
        parse_mode="Markdown",
    )
    return EDIT_CONTENT


async def edit_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    path = Path(ctx.user_data["edit_post_path"])
    path.write_text(update.message.text, encoding="utf-8")
    shell("systemctl restart blog")
    await update.message.reply_text(f"Updated ✓ {path.name}")
    return ConversationHandler.END


async def edit_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── /restart & /status ────────────────────────────────────────────────────────

async def cmd_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    code, out = shell("systemctl restart blog")
    await update.message.reply_text("Restarted ✓" if code == 0 else f"Error:\n{out}")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    _, out = shell("systemctl status blog --no-pager -l --lines=8")
    await update.message.reply_text(f"```\n{out}\n```", parse_mode="Markdown")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    new_conv = ConversationHandler(
        entry_points=[
            CommandHandler("newpost",  newpost_start),
            CommandHandler("newessay", newessay_start),
        ],
        states={
            TITLE:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_title)],
            TAGS:          [
                CommandHandler("skip", skip_tags),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_tags),
            ],
            CONTENT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_content)],
            ASK_SUMMARY:   [
                CommandHandler("skip", skip_summary),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_summary),
            ],
            ASK_SERIES:    [
                CommandHandler("skip", skip_series),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_series),
            ],
            FINAL_CONFIRM: [CallbackQueryHandler(new_final, pattern=r"^new:")],
        },
        fallbacks=[CommandHandler("cancel", new_cancel)],
    )

    pages_conv = ConversationHandler(
        entry_points=[CommandHandler("pages", cmd_pages)],
        states={
            PAGE_PICK:    [CallbackQueryHandler(page_pick, pattern=r"^page:")],
            PAGE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, page_content)],
        },
        fallbacks=[CommandHandler("cancel", pages_cancel)],
    )

    book_conv = ConversationHandler(
        entry_points=[CommandHandler("newbook", newbook_start)],
        states={
            BOOK_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, book_title)],
            BOOK_AUTHOR: [
                CommandHandler("skip", skip_author),
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_author),
            ],
            BOOK_COVER: [
                CommandHandler("skip", skip_cover),
                MessageHandler(filters.PHOTO | filters.Document.ALL, book_cover),
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_cover),
            ],
            BOOK_SUMMARY: [
                CommandHandler("skip", skip_summary_book),
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_summary),
            ],
            BOOK_NOTES:   [MessageHandler(filters.TEXT & ~filters.COMMAND, book_notes)],
            BOOK_CONFIRM: [CallbackQueryHandler(book_final, pattern=r"^book:")],
        },
        fallbacks=[CommandHandler("cancel", book_cancel)],
    )

    edit_conv = ConversationHandler(
        entry_points=[
            CommandHandler("edit",      cmd_edit),
            CommandHandler("editessay", cmd_editessay),
            CommandHandler("editbook",  cmd_editbook),
        ],
        states={
            EDIT_PICK:    [CallbackQueryHandler(edit_pick, pattern=r"^edit:")],
            EDIT_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_content)],
        },
        fallbacks=[CommandHandler("cancel", edit_cancel)],
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(new_conv)
    application.add_handler(pages_conv)
    application.add_handler(book_conv)
    application.add_handler(edit_conv)
    application.add_handler(CommandHandler("drafts", cmd_drafts))
    application.add_handler(CallbackQueryHandler(draft_pick,    pattern=r"^draft:"))
    application.add_handler(CallbackQueryHandler(draft_publish, pattern=r"^dpub:"))
    application.add_handler(CommandHandler("posts",  cmd_posts))
    application.add_handler(CommandHandler("essays", cmd_essays))
    application.add_handler(CommandHandler("books",    cmd_books))
    application.add_handler(CommandHandler("delete",   cmd_delete))
    application.add_handler(CommandHandler("delessay", cmd_delessay))
    application.add_handler(CommandHandler("delbook",  cmd_delbook))
    application.add_handler(CallbackQueryHandler(delete_pick,    pattern=r"^del:"))
    application.add_handler(CallbackQueryHandler(delete_confirm, pattern=r"^delconf:"))
    application.add_handler(CommandHandler("restart", cmd_restart))
    application.add_handler(CommandHandler("status",  cmd_status))

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
