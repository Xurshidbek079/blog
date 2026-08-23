import re
import io
import os
import difflib
import hashlib
import hmac
import secrets
import subprocess
from functools import lru_cache
from pathlib import Path
from datetime import date, datetime, timezone
from flask import Flask, render_template, abort, request, Response, redirect, session
from markupsafe import Markup, escape
import markdown
from PIL import Image, ImageOps
import yaml

UPLOAD_MAX = 16 * 1024 * 1024      # hard ceiling on any request body
IMAGE_MAX_W = 1600                 # uploads wider than this are downscaled

app = Flask(__name__)
app.url_map.strict_slashes = False
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=UPLOAD_MAX,
)

CONTENT = Path("content")
IMAGES  = Path("static/img")       # admin-uploaded essay images
POSTS   = Path("content/posts")
ESSAYS  = Path("content/essays")   # unlisted, served at root: /<slug>
DRAFTS  = Path("content/drafts")   # unpublished blog posts

# ── Admin config ──────────────────────────────────────────────────────────────
_ADMIN_PATH = os.environ.get("ADMIN_PATH", "").strip("/")
_ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "")

# Stable secret key so sessions survive gunicorn restarts
_secret_src = os.environ.get("SECRET_KEY") or _ADMIN_PASS
app.secret_key = hashlib.sha256(_secret_src.encode()).digest() if _secret_src else os.urandom(24)

# ── Reserved root slugs ───────────────────────────────────────────────────────
# Essays live at the site root (/<slug>), so a slug must never collide with a real
# page. Flask already ranks static rules above the dynamic /<slug> rule, so an essay
# named "about" could not hijack /about — but it would be permanently unreachable,
# which is worse than being told at publish time. Both writers check this set.
_RESERVED_SLUGS = {
    "blog", "about", "now", "contact", "projects", "tools",
    "feed.xml", "sitemap.xml", "static", "robots.txt", "favicon.ico", "admin",
}
if _ADMIN_PATH:
    _RESERVED_SLUGS.add(_ADMIN_PATH.lower())


# -- CSRF + security headers ------------------------------------------------------
def _csrf_token() -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok


def _check_csrf() -> None:
    good = session.get("_csrf", "")
    sent = request.form.get("_csrf", "")
    if not good or not hmac.compare_digest(sent, good):
        abort(400)


@app.context_processor
def inject_csrf():
    return {"csrf_token": _csrf_token}


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return resp


def _derive_slug(path: Path, meta: dict) -> str:
    if meta.get("slug"):
        return str(meta["slug"])
    return re.sub(r'^\d{4}-\d{2}-\d{2}-', '', path.stem)


def parse_post(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2]
    else:
        meta, body = {}, text
    meta["content"] = markdown.markdown(body, extensions=["fenced_code", "tables", "footnotes"])
    meta["slug"] = _derive_slug(path, meta)
    meta.setdefault("published", True)
    meta.setdefault("tags", [])
    meta.setdefault("type", None)
    meta.setdefault("series", None)
    meta.setdefault("summary", None)
    return meta


@lru_cache(maxsize=None)
def get_slug_map() -> dict:
    result = {}
    if not POSTS.exists():
        return result
    for p in POSTS.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) or {} if text.startswith("---") else {}
        result[_derive_slug(p, meta)] = p
    return result


@lru_cache(maxsize=None)
def get_posts(tag: str | None = None) -> list[dict]:
    if not POSTS.exists():
        return []
    paths = sorted(POSTS.glob("*.md"), key=lambda p: p.stem, reverse=True)
    posts = [parse_post(p) for p in paths]
    posts = [p for p in posts if p.get("published")]
    if tag:
        posts = [p for p in posts if tag in p.get("tags", [])]
    return posts


@lru_cache(maxsize=None)
def get_essay_slug_map() -> dict:
    """{slug: Path} for essays. Includes unpublished ones — the view filters them."""
    result = {}
    if not ESSAYS.exists():
        return result
    for p in ESSAYS.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) or {} if text.startswith("---") else {}
        result[_derive_slug(p, meta)] = p
    return result


@lru_cache(maxsize=None)
def _render_md(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        return ""
    return markdown.markdown(
        path.read_text(encoding="utf-8"),
        extensions=["fenced_code", "tables"],
    )


def read_md(filename: str) -> str:
    return _render_md(str(CONTENT / filename))


@lru_cache(maxsize=None)
def read_yaml(filename: str):
    path = CONTENT / filename
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


_LINKIFY_RE = re.compile(
    r'\[(?P<txt>[^\]]+)\]\((?P<murl>https?://[^\s)]+)\)'          # [text](url)
    r'|(?P<url>https?://[^\s<]+)'                                  # bare URL
    r'|(?P<dom>\b(?:[a-z0-9-]+\.)+(?:uz|com|org|net|io|dev|me|co|app|ai|xyz)\b)',  # bare domain
    re.I,
)


def _linkify_sub(m: re.Match) -> str:
    if m.group("txt"):
        return f'<a href="{m.group("murl")}">{m.group("txt")}</a>'
    if m.group("url"):
        u = m.group("url")
        return f'<a href="{u}">{u}</a>'
    d = m.group("dom")
    return f'<a href="https://{d}">{d}</a>'


@app.template_filter("linkify")
def linkify_filter(text):
    """Escape text, then turn markdown links, bare URLs, and bare domains into <a> tags."""
    if not text:
        return ""
    return Markup(_LINKIFY_RE.sub(_linkify_sub, str(escape(text))))


@app.template_filter("rss_date")
def rss_date_filter(d):
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    elif isinstance(d, date):
        d = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    else:
        return str(d)
    return d.strftime("%a, %d %b %Y %H:%M:%S +0000")


@app.route("/")
def home():
    return render_template("home.html", recent_posts=get_posts()[:5])


@app.route("/blog")
def blog():
    tag = request.args.get("tag") or None
    return render_template("blog.html", posts=get_posts(tag), active_tag=tag)


@app.route("/blog/<slug>")
def post(slug):
    path = get_slug_map().get(slug)
    if path is None:
        abort(404)
    return render_template("post.html", post=parse_post(path))


@app.route("/about")
def about():
    return render_template("page.html", title="About", content=read_md("about.md"))


@app.route("/now")
def now():
    return render_template("page.html", title="Now", content=read_md("now.md"))


@app.route("/contact")
def contact():
    return render_template("page.html", title="Contact", content=read_md("contact.md"))


@app.route("/projects")
def projects():
    return render_template("projects.html", projects=read_yaml("projects.yaml"))


@app.route("/tools")
def tools():
    return render_template("tools.html", sections=read_yaml("tools.yaml"))


@app.route("/feed.xml")
def feed():
    posts = get_posts()
    base = request.host_url.rstrip("/")
    xml = render_template("feed.xml", posts=posts, base=base)
    return Response(xml, mimetype="application/rss+xml")


@app.route("/sitemap.xml")
def sitemap():
    posts = get_posts()
    base = request.host_url.rstrip("/")
    static_routes = ["/", "/blog", "/about", "/now", "/contact", "/projects", "/tools"]
    xml = render_template("sitemap.xml", posts=posts, static_routes=static_routes, base=base)
    return Response(xml, mimetype="application/xml")


def _near_miss(slug: str) -> str | None:
    """The published essay slug someone was probably aiming for, or None.

    The cutoff is deliberately high and short slugs are skipped: a scanner asking for
    /wp-login gets a plain 404, and only a believable typo of a real essay earns the joke.
    """
    if len(slug) < 4:
        return None
    live = [s for s, p in get_essay_slug_map().items() if parse_post(p).get("published")]
    hit = difflib.get_close_matches(slug.lower(), live, n=1, cutoff=0.8)
    return hit[0] if hit else None


@app.route("/<slug>")
def essay(slug):
    """Unlisted essay served at the site root, e.g. /mutolaa.

    Deliberately absent from /blog, the homepage, feed.xml and sitemap.xml — the only
    way in is the direct link. Flask matches the static rules above this one first, so
    /about and friends are unaffected.
    """
    if slug.lower() in _RESERVED_SLUGS:
        abort(404)
    path = get_essay_slug_map().get(slug)
    if path is None:
        near = _near_miss(slug)
        if near:
            return render_template("oops.html", correct=near), 404
        abort(404)
    data = parse_post(path)
    if not data.get("published"):
        abort(404)
    return render_template("essay.html", post=data)


@app.errorhandler(413)
def too_large(e):
    return {"error": "file too large — 16 MB max"}, 413


@app.errorhandler(404)
def not_found(e):
    return render_template("oops.html", correct=None), 404


# ── Admin panel ───────────────────────────────────────────────────────────────
def _is_admin() -> bool:
    return bool(_ADMIN_PASS) and session.get("_adm") is True


def _admin_slugify(text: str) -> str:
    text = re.sub(r"[ʻʼʼ''‘’`]", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _kind_dir(kind: str) -> Path:
    """Content directory for an admin 'kind'. Anything unrecognised means blog posts."""
    return ESSAYS if kind == "essay" else POSTS


def _kind_url(kind: str, slug: str) -> str:
    """Public URL a published item of this kind ends up at."""
    return f"/{slug}" if kind == "essay" else f"/blog/{slug}"


def _load_essays_meta(directory: Path, draft: bool = False) -> list[dict]:
    """Return lightweight list of everything in `directory` for the admin sidebar."""
    if not directory.exists():
        return []
    result = []
    for p in sorted(directory.glob("*.md"), reverse=True):
        text = p.read_text(encoding="utf-8")
        meta: dict = {}
        if text.startswith("---"):
            parts = text.split("---", 2)
            meta = yaml.safe_load(parts[1]) or {}
        slug = meta.get("slug") or re.sub(r'^\d{4}-\d{2}-\d{2}-', '', p.stem)
        result.append({
            "title":     meta.get("title", p.stem),
            "slug":      str(slug),
            "date":      str(meta.get("date", "")),
            "published": meta.get("published", True),
            "filename":  p.name,
            "draft":     draft,
        })
    return result


def _admin_listing(kind: str) -> list[dict]:
    """Everything the write page should offer to edit, newest first.

    Blog drafts live in their own directory, so they have to be merged in here;
    unpublished essays already sit alongside published ones and carry their own
    flag, so the essay side needs no extra pass.
    """
    if kind == "essay":
        return _load_essays_meta(ESSAYS)
    items = _load_essays_meta(POSTS) + _load_essays_meta(DRAFTS, draft=True)
    return sorted(items, key=lambda e: (e["date"], e["title"]), reverse=True)


def _store_image(fs) -> str | None:
    """Save an uploaded image under static/img/, or None if it is not one.

    Everything is re-encoded rather than trusted: Pillow parsing the bytes is what
    proves the upload is an image at all, and re-saving drops EXIF (including GPS)
    on the way out. Wide photos are downscaled — the server is a long way from most
    readers, so a 4000px phone shot would cost seconds for no visible gain.
    Animated GIFs are stored byte-for-byte, since re-encoding would flatten them.
    """
    raw = fs.read(UPLOAD_MAX + 1)
    if not raw or len(raw) > UPLOAD_MAX:
        return None
    try:
        Image.open(io.BytesIO(raw)).verify()      # structural check; consumes the file
        im = Image.open(io.BytesIO(raw))          # ...so reopen for the real work
        fmt = (im.format or "").upper()
    except Exception:
        return None
    if fmt not in {"JPEG", "PNG", "GIF", "WEBP"}:
        return None

    stem = _admin_slugify(Path(fs.filename or "image").stem)[:40] or "image"
    name = f"{date.today().isoformat()}-{stem}-{secrets.token_hex(3)}"
    IMAGES.mkdir(parents=True, exist_ok=True)

    if fmt == "GIF":
        out = IMAGES / f"{name}.gif"
        out.write_bytes(raw)
        return f"/{out.as_posix()}"

    im = ImageOps.exif_transpose(im)               # apply camera rotation, then lose it
    if im.width > IMAGE_MAX_W:
        height = round(im.height * IMAGE_MAX_W / im.width)
        im = im.resize((IMAGE_MAX_W, height), Image.LANCZOS)

    if im.mode in {"RGBA", "LA"} or (im.mode == "P" and "transparency" in im.info):
        out = IMAGES / f"{name}.png"
        im.convert("RGBA").save(out, "PNG", optimize=True)
    else:
        out = IMAGES / f"{name}.jpg"
        im.convert("RGB").save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return f"/{out.as_posix()}"


def _find_essay(slug: str, directory: Path):
    """Return (path, meta, body) for an item in `directory` matching slug, or (None, {}, '')."""
    if not directory.exists():
        return None, {}, ""
    for p in directory.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        meta: dict = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n")
        file_slug = meta.get("slug") or re.sub(r'^\d{4}-\d{2}-\d{2}-', '', p.stem)
        if str(file_slug) == slug:
            return p, meta, body
    return None, {}, ""


if _ADMIN_PATH and _ADMIN_PASS:

    @app.route(f"/{_ADMIN_PATH}", methods=["GET", "POST"])
    def _admin_login():
        if _is_admin():
            return redirect(f"/{_ADMIN_PATH}/write")
        error = False
        if request.method == "POST":
            _check_csrf()
            if hmac.compare_digest(request.form.get("p", ""), _ADMIN_PASS):
                session["_adm"] = True
                return redirect(f"/{_ADMIN_PATH}/write")
            error = True
        return render_template("admin_login.html", error=error, ap=_ADMIN_PATH)

    @app.route(f"/{_ADMIN_PATH}/write")
    def _admin_write():
        if not _is_admin():
            return redirect(f"/{_ADMIN_PATH}")
        ok    = request.args.get("ok")
        slug  = request.args.get("slug", "")
        draft = request.args.get("draft", "0") == "1"
        kind  = "essay" if request.args.get("kind") == "essay" else "post"
        return render_template(
            "admin_editor.html",
            ap=_ADMIN_PATH, ok=ok, slug=slug, draft=draft, kind=kind,
            err=request.args.get("err"),
            live_url=_kind_url(kind, slug),
            edit_mode=False, essays=_admin_listing(kind),
            edit_title="", edit_tags="", edit_content="", edit_slug="",
        )

    @app.route(f"/{_ADMIN_PATH}/edit/<slug>")
    def _admin_edit(slug):
        if not _is_admin():
            return redirect(f"/{_ADMIN_PATH}")
        kind = "essay" if request.args.get("kind") == "essay" else "post"
        is_draft = kind == "post" and request.args.get("draft") == "1"
        path, meta, body = _find_essay(slug, DRAFTS if is_draft else _kind_dir(kind))
        if path is None:
            abort(404)
        tags_str = ", ".join(str(t) for t in meta.get("tags", []))
        ok = request.args.get("ok")
        return render_template(
            "admin_editor.html",
            ap=_ADMIN_PATH, ok=ok, slug=slug, draft=False, kind=kind,
            live_url=_kind_url(kind, slug), is_draft=is_draft,
            edit_mode=True, essays=[],
            edit_title=meta.get("title", ""),
            edit_tags=tags_str,
            edit_content=body,
            edit_slug=slug,
            edit_filename=path.name,
            edit_published=meta.get("published", True) is not False,
        )

    @app.route(f"/{_ADMIN_PATH}/publish", methods=["POST"])
    def _admin_publish():
        if not _is_admin():
            abort(403)
        _check_csrf()
        title   = request.form.get("title", "").strip()
        tags_r  = request.form.get("tags", "").strip()
        content = request.form.get("content", "").strip()
        action  = request.form.get("action", "publish")
        kind    = "essay" if request.form.get("kind") == "essay" else "post"
        if not title or not content:
            abort(400)
        slug      = _admin_slugify(title)
        date_str  = date.today().isoformat()
        fname     = f"{date_str}-{slug}.md"
        tags      = [_admin_slugify(t) for t in tags_r.split(",") if t.strip()]
        tags_yaml = "[" + ", ".join(tags) + "]" if tags else "[]"
        # Essays sit at the site root, so their slug must not collide with a real page.
        if kind == "essay" and (not slug or slug in _RESERVED_SLUGS):
            return redirect(f"/{_ADMIN_PATH}/write?kind=essay&err=slug")
        # An essay has no list to hide from, so "draft" means published: false (404s
        # publicly, still editable here). A blog post drafts to content/drafts/ instead.
        published = "false" if (kind == "essay" and action == "draft") else "true"
        fm = (
            f'---\ntitle: "{title}"\ndate: {date_str}\nslug: {slug}\n'
            f"published: {published}\ntags: {tags_yaml}\n---\n\n{content}\n"
        )
        if kind == "essay":
            target = ESSAYS
        else:
            target = DRAFTS if action == "draft" else POSTS
        target.mkdir(parents=True, exist_ok=True)
        (target / fname).write_text(fm, encoding="utf-8")
        if action == "publish":
            subprocess.run(["systemctl", "restart", "blog"], capture_output=True)
        is_draft = "1" if action == "draft" else "0"
        return redirect(
            f"/{_ADMIN_PATH}/write?ok=1&slug={slug}&draft={is_draft}&kind={kind}"
        )

    @app.route(f"/{_ADMIN_PATH}/save", methods=["POST"])
    def _admin_save():
        if not _is_admin():
            abort(403)
        _check_csrf()
        slug    = request.form.get("_slug", "").strip()
        fname   = request.form.get("_filename", "").strip()
        title   = request.form.get("title", "").strip()
        tags_r  = request.form.get("tags", "").strip()
        content = request.form.get("content", "").strip()
        kind    = "essay" if request.form.get("kind") == "essay" else "post"
        action  = request.form.get("action", "save")
        if not slug or not fname or not title or not content:
            abort(400)
        is_draft = kind == "post" and request.form.get("_draft") == "1"
        path = (DRAFTS if is_draft else _kind_dir(kind)) / fname
        if not path.exists():
            abort(404)
        # Preserve original date and slug — only update title, tags, body
        text = path.read_text(encoding="utf-8")
        meta: dict = {}
        if text.startswith("---"):
            parts = text.split("---", 2)
            meta = yaml.safe_load(parts[1]) or {}
        orig_slug    = meta.get("slug") or re.sub(r'^\d{4}-\d{2}-\d{2}-', '', path.stem)
        orig_date    = str(meta.get("date", date.today().isoformat()))
        tags         = [_admin_slugify(t) for t in tags_r.split(",") if t.strip()]
        tags_yaml    = "[" + ", ".join(tags) + "]" if tags else "[]"
        # Saving must not silently publish an unpublished essay — only the Publish
        # button does that. Everything else keeps whatever state the file already had.
        was_published = meta.get("published", True) is not False
        published     = "true" if (action == "publish" or was_published) else "false"
        fm = (
            f'---\ntitle: "{title}"\ndate: {orig_date}\nslug: {orig_slug}\n'
            f"published: {published}\ntags: {tags_yaml}\n---\n\n{content}\n"
        )
        # Publishing a draft moves the file out of content/drafts/ into the live
        # directory. Saving leaves it a draft, wherever it already is.
        if is_draft and action == "publish":
            POSTS.mkdir(parents=True, exist_ok=True)
            (POSTS / fname).write_text(fm, encoding="utf-8")
            path.unlink()
            is_draft = False
        else:
            path.write_text(fm, encoding="utf-8")
        subprocess.run(["systemctl", "restart", "blog"], capture_output=True)
        still_draft = "&draft=1" if is_draft else ""
        return redirect(
            f"/{_ADMIN_PATH}/edit/{orig_slug}?ok=1&kind={kind}{still_draft}"
        )

    @app.route(f"/{_ADMIN_PATH}/upload", methods=["POST"])
    def _admin_upload():
        """Take an image from the editor, normalise it, return its public URL.

        Answers JSON because the editor posts here with fetch() and splices the
        returned URL into the textarea. No restart: images are static files, so
        nginx serves them the moment they land.
        """
        if not _is_admin():
            abort(403)
        _check_csrf()
        fs = request.files.get("image")
        if fs is None:
            return {"error": "no file"}, 400
        url = _store_image(fs)
        if url is None:
            return {"error": "not a usable image — jpg, png, gif or webp, 16 MB max"}, 400
        return {"url": url}

    @app.route(f"/{_ADMIN_PATH}/logout")
    def _admin_logout():
        session.pop("_adm", None)
        return redirect(f"/{_ADMIN_PATH}")


if __name__ == "__main__":
    app.run(debug=False)
