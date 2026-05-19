#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

BOT_TOKEN      = os.environ["BOT_TOKEN"]
ADMIN_ID       = int(os.environ["ADMIN_ID"])
BLOG_DIR       = Path("/root/blog")
ESSAYS_DIR     = BLOG_DIR / "content/posts"   # /essays on site
BLOG_POSTS_DIR = BLOG_DIR / "content/blog"    # /blog on site
DRAFTS_DIR     = BLOG_DIR / "content/drafts"
CONTENT_DIR    = BLOG_DIR / "content"

# ── Conversation states ────────────────────────────────────────────────────────
(TITLE, TAGS, CONTENT,
 ASK_UZ, ASK_CYR,
 FINAL_CONFIRM) = range(6)

(PAGE_PICK, PAGE_LANG, PAGE_CONTENT) = range(6, 9)

PAGES = {
    "About":    "about.md",
    "Now":      "now.md",
    "Contact":  "contact.md",
    "Projects": "projects.yaml",
    "Books":    "books.yaml",
    "Tools":    "tools.yaml",
}

_LANG_VARIANT = re.compile(r'\.(uz|uz_cyr)\.md$')


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def shell(cmd: str) -> tuple[int, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def base_posts(directory: Path):
    return sorted(
        [f for f in directory.glob("*.md") if not _LANG_VARIANT.search(f.name)],
        reverse=True,
    )


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "Blog admin\n\n"
        "/newessay — write a new essay (→ /essays)\n"
        "/newpost — write a new blog post (→ /blog)\n"
        "/drafts — list & publish drafts\n"
        "/essays — recent published essays\n"
        "/posts — recent published blog posts\n"
        "/delete — delete an essay or blog post\n"
        "/pages — edit a page (About, Now, Contact, etc.)\n"
        "/restart — restart blog service\n"
        "/status — service status"
    )


# ── /newessay and /newpost conversations ──────────────────────────────────────

async def newessay_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    ctx.user_data["post_dir"] = ESSAYS_DIR
    ctx.user_data["post_type"] = "essay"
    await update.message.reply_text("Essay title:")
    return TITLE


async def newpost_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END
    ctx.user_data["post_dir"] = BLOG_POSTS_DIR
    ctx.user_data["post_type"] = "post"
    await update.message.reply_text("Blog post title:")
    return TITLE


async def got_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("Tags (comma-separated) or /skip:")
    return TAGS


async def got_tags(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    ctx.user_data["tags"] = [slugify(t) for t in raw.split(",") if t.strip()]
    await update.message.reply_text("Post content (Markdown):")
    return CONTENT


async def skip_tags(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["tags"] = []
    await update.message.reply_text("Post content (Markdown):")
    return CONTENT


async def got_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["en_content"] = update.message.text
    await update.message.reply_text(
        "🇺🇿 Uzbek Latin translation?\nSend the text or /skip:"
    )
    return ASK_UZ


async def got_uz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["uz_content"] = update.message.text
    await update.message.reply_text(
        "🇺🇿 Uzbek Cyrillic translation?\nSend the text or /skip:"
    )
    return ASK_CYR


async def skip_uz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["uz_content"] = None
    await update.message.reply_text(
        "🇺🇿 Uzbek Cyrillic translation?\nSend the text or /skip:"
    )
    return ASK_CYR


async def got_cyr(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["cyr_content"] = update.message.text
    return await _show_final_confirm(update.message, ctx)


async def skip_cyr(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["cyr_content"] = None
    return await _show_final_confirm(update.message, ctx)


async def _show_final_confirm(message, ctx):
    title     = ctx.user_data["title"]
    tags      = ctx.user_data["tags"]
    post_type = ctx.user_data.get("post_type", "essay")
    langs  = "EN"
    if ctx.user_data.get("uz_content"):  langs += " + UZ"
    if ctx.user_data.get("cyr_content"): langs += " + ЎЗ"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Publish now",   callback_data="new:publish"),
        InlineKeyboardButton("Save as draft", callback_data="new:draft"),
        InlineKeyboardButton("Cancel",        callback_data="new:cancel"),
    ]])
    await message.reply_text(
        f"*{title}*\nType: {post_type}\nTags: {', '.join(tags) or 'none'}\nLanguages: {langs}",
        parse_mode="Markdown",
        reply_markup=kb,
    )
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

    def frontmatter(body: str) -> str:
        return (
            f"---\ntitle: {title}\ndate: {date_str}\nslug: {slug}\n"
            f"published: true\ntags: {tags_yaml}\n---\n\n{body}"
        )

    post_dir  = ctx.user_data.get("post_dir", ESSAYS_DIR)
    post_type = ctx.user_data.get("post_type", "essay")
    route     = "/blog" if post_type == "post" else "/essays"

    target = post_dir if action == "publish" else DRAFTS_DIR
    target.mkdir(parents=True, exist_ok=True)

    (target / fname).write_text(frontmatter(ctx.user_data["en_content"]), encoding="utf-8")
    if ctx.user_data.get("uz_content"):
        (target / fname.replace(".md", ".uz.md")).write_text(
            frontmatter(ctx.user_data["uz_content"]), encoding="utf-8"
        )
    if ctx.user_data.get("cyr_content"):
        (target / fname.replace(".md", ".uz_cyr.md")).write_text(
            frontmatter(ctx.user_data["cyr_content"]), encoding="utf-8"
        )

    if action == "publish":
        shell("systemctl restart blog")
        await q.edit_message_text(f"Published ✓\n{route}/{slug}")
    else:
        await q.edit_message_text(f"Draft saved ({post_type}): {fname}")
    return ConversationHandler.END


async def new_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


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
    ctx.user_data["draft"] = fname
    preview  = path.read_text(encoding="utf-8")[:500]
    uz_ok    = (DRAFTS_DIR / fname.replace(".md", ".uz.md")).exists()
    cyr_ok   = (DRAFTS_DIR / fname.replace(".md", ".uz_cyr.md")).exists()
    langs    = "EN" + (" + UZ" if uz_ok else "") + (" + ЎЗ" if cyr_ok else "")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("→ Essay (/essays)", callback_data="dpub:essay"),
        InlineKeyboardButton("→ Blog (/blog)",    callback_data="dpub:blog"),
        InlineKeyboardButton("Cancel",            callback_data="dpub:no"),
    ]])
    await q.edit_message_text(
        f"`{fname}` ({langs})\n\n{preview}\n\nPublish to:", parse_mode="Markdown", reply_markup=kb
    )


async def draft_publish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    if q.data == "dpub:no":
        await q.edit_message_text("Cancelled.")
        return
    ctx.user_data["draft_dest"] = BLOG_POSTS_DIR if q.data == "dpub:blog" else ESSAYS_DIR
    fname = ctx.user_data.get("draft")
    if not fname:
        await q.edit_message_text("No draft selected.")
        return
    dest_dir = ctx.user_data.get("draft_dest", ESSAYS_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    published = []
    for variant in [fname, fname.replace(".md", ".uz.md"), fname.replace(".md", ".uz_cyr.md")]:
        src = DRAFTS_DIR / variant
        if src.exists():
            (dest_dir / variant).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            published.append(variant)
    shell("systemctl restart blog")
    await q.edit_message_text("Published ✓\n" + "\n".join(published))


# ── /essays and /posts ────────────────────────────────────────────────────────

async def cmd_essays(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    files = base_posts(ESSAYS_DIR)[:10]
    if not files:
        await update.message.reply_text("No essays yet.")
        return
    await update.message.reply_text("Recent essays:\n" + "\n".join(f.stem for f in files))


async def cmd_posts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    BLOG_POSTS_DIR.mkdir(parents=True, exist_ok=True)
    files = base_posts(BLOG_POSTS_DIR)[:10]
    if not files:
        await update.message.reply_text("No blog posts yet.")
        return
    await update.message.reply_text("Recent blog posts:\n" + "\n".join(f.stem for f in files))


# ── /delete ───────────────────────────────────────────────────────────────────

async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    essays    = [("[E] " + f.name, f"del:e:{f.name}") for f in base_posts(ESSAYS_DIR)]
    blogposts = [("[B] " + f.name, f"del:b:{f.name}") for f in base_posts(BLOG_POSTS_DIR)]
    all_files = essays + blogposts
    if not all_files:
        await update.message.reply_text("No posts to delete.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=cb)]
        for label, cb in all_files
    ])
    await update.message.reply_text("[E]=Essay  [B]=Blog post\nSelect to delete:", reply_markup=kb)


async def delete_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    _, kind, fname = q.data.split(":", 2)
    src_dir = ESSAYS_DIR if kind == "e" else BLOG_POSTS_DIR
    if not (src_dir / fname).exists():
        await q.edit_message_text("Not found.")
        return
    ctx.user_data["delete"]     = fname
    ctx.user_data["delete_dir"] = src_dir
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, delete", callback_data="delconf:yes"),
        InlineKeyboardButton("Cancel",      callback_data="delconf:no"),
    ]])
    await q.edit_message_text(
        f"Delete *{fname}* and all language variants?",
        parse_mode="Markdown", reply_markup=kb,
    )


async def delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        return
    if q.data == "delconf:no":
        await q.edit_message_text("Cancelled.")
        return
    fname   = ctx.user_data.get("delete")
    src_dir = ctx.user_data.get("delete_dir", ESSAYS_DIR)
    if not fname:
        await q.edit_message_text("No post selected.")
        return
    deleted = []
    for variant in [fname, fname.replace(".md", ".uz.md"), fname.replace(".md", ".uz_cyr.md")]:
        p = src_dir / variant
        if p.exists():
            p.unlink()
            deleted.append(variant)
    shell("systemctl restart blog")
    await q.edit_message_text("Deleted ✓\n" + "\n".join(deleted))


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

    # YAML pages have no language variants — go straight to content
    if fname.endswith(".yaml"):
        path = CONTENT_DIR / fname
        current = path.read_text(encoding="utf-8") if path.exists() else "(empty)"
        if len(current) > 3000:
            current = current[:3000] + "\n…(truncated)"
        await q.edit_message_text(
            f"*{fname}* (current):\n\n```\n{current}\n```\n\nSend full new YAML content, or /cancel:",
            parse_mode="Markdown",
        )
        return PAGE_CONTENT

    # Markdown pages: pick language first
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("EN 🇬🇧",        callback_data="plang:en"),
        InlineKeyboardButton("UZ (Latin)",    callback_data="plang:uz"),
        InlineKeyboardButton("ЎЗ (Cyrillic)", callback_data="plang:uz_cyr"),
    ]])
    await q.edit_message_text(
        f"*{fname}* — which language to edit?",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return PAGE_LANG


async def page_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data.split(":", 1)[1]
    ctx.user_data["edit_lang"] = lang

    fname = ctx.user_data["edit_page"]
    stem, ext = fname.rsplit(".", 1)
    if lang == "en":
        file_path = CONTENT_DIR / fname
    elif lang == "uz":
        file_path = CONTENT_DIR / f"{stem}.uz.{ext}"
    else:
        file_path = CONTENT_DIR / f"{stem}.uz_cyr.{ext}"

    ctx.user_data["edit_path"] = str(file_path)
    current = file_path.read_text(encoding="utf-8") if file_path.exists() else "(empty)"
    if len(current) > 3000:
        current = current[:3000] + "\n…(truncated)"

    lang_label = {"en": "EN 🇬🇧", "uz": "UZ (Latin)", "uz_cyr": "ЎЗ (Cyrillic)"}[lang]
    await q.edit_message_text(
        f"*{fname}* — {lang_label} (current):\n\n```\n{current}\n```\n\nSend new Markdown content, or /cancel:",
        parse_mode="Markdown",
    )
    return PAGE_CONTENT


async def page_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fname = ctx.user_data.get("edit_page", "")
    new_text = update.message.text

    if fname.endswith(".yaml"):
        (CONTENT_DIR / fname).write_text(new_text, encoding="utf-8")
        shell("systemctl restart blog")
        await update.message.reply_text(f"Saved ✓ {fname}")
        return ConversationHandler.END

    file_path = Path(ctx.user_data["edit_path"])
    file_path.write_text(new_text, encoding="utf-8")
    shell("systemctl restart blog")
    await update.message.reply_text(f"Saved ✓ {file_path.name}")
    return ConversationHandler.END


async def pages_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
            CommandHandler("newessay", newessay_start),
            CommandHandler("newpost",  newpost_start),
        ],
        states={
            TITLE:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_title)],
            TAGS:          [
                CommandHandler("skip", skip_tags),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_tags),
            ],
            CONTENT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_content)],
            ASK_UZ:        [
                CommandHandler("skip", skip_uz),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_uz),
            ],
            ASK_CYR:       [
                CommandHandler("skip", skip_cyr),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_cyr),
            ],
            FINAL_CONFIRM: [CallbackQueryHandler(new_final, pattern=r"^new:")],
        },
        fallbacks=[CommandHandler("cancel", new_cancel)],
    )

    pages_conv = ConversationHandler(
        entry_points=[CommandHandler("pages", cmd_pages)],
        states={
            PAGE_PICK:    [CallbackQueryHandler(page_pick, pattern=r"^page:")],
            PAGE_LANG:    [CallbackQueryHandler(page_lang, pattern=r"^plang:")],
            PAGE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, page_content)],
        },
        fallbacks=[CommandHandler("cancel", pages_cancel)],
    )

    application.add_handler(CommandHandler("start",     cmd_start))
    application.add_handler(new_conv)
    application.add_handler(pages_conv)
    application.add_handler(CommandHandler("drafts",   cmd_drafts))
    application.add_handler(CallbackQueryHandler(draft_pick,    pattern=r"^draft:"))
    application.add_handler(CallbackQueryHandler(draft_publish, pattern=r"^dpub:"))
    application.add_handler(CommandHandler("essays",   cmd_essays))
    application.add_handler(CommandHandler("posts",    cmd_posts))
    application.add_handler(CommandHandler("delete",   cmd_delete))
    application.add_handler(CallbackQueryHandler(delete_pick,    pattern=r"^del:"))
    application.add_handler(CallbackQueryHandler(delete_confirm, pattern=r"^delconf:"))
    application.add_handler(CommandHandler("restart",  cmd_restart))
    application.add_handler(CommandHandler("status",   cmd_status))

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
