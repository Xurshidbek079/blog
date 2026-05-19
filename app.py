import re
from functools import lru_cache
from pathlib import Path
from datetime import date, datetime, timezone
from flask import Flask, render_template, abort, request, Response, redirect
import markdown
import yaml

app = Flask(__name__)
app.url_map.strict_slashes = False

CONTENT = Path("content")
BLOG    = Path("content/blog")
POEMS   = Path("content/poems")

TRANSLATIONS = {
    "en": {
        "nav_home": "Main",
        "nav_blog": "Blog",
        "nav_essays": "Essays",
        "nav_poems": "Poems",
        "nav_projects": "Projects",
        "nav_books": "Books",
        "nav_tools": "Tools",
        "nav_now": "Now",
        "nav_about": "About",
        "nav_contact": "Contact",
        "home_tagline": "Software engineer. I write about things I'm learning and building.",
        "home_recent": "Recent essays",
        "home_all_essays": "→ All essays",
        "home_explore": "Explore",
        "home_contact_invite": "Have something to say? I'd love to hear from you.",
        "essays_title": "Essays",
        "essays_tag_prefix": "Tag:",
        "essays_tag_clear": "clear",
        "essays_none": "No essays yet.",
        "essays_none_tagged": "No essays tagged",
        "about_title": "About",
        "now_title": "Now",
        "contact_title": "Contact",
        "projects_title": "Projects",
        "books_title": "Books",
        "books_reading": "Reading now",
        "books_done": "Done",
        "books_want": "Want to read",
        "tools_title": "Tools",
        "post_back": "← Essays",
        "post_back_blog": "← Blog",
        "post_back_poems": "← Poems",
        "poems_title": "Poems",
        "poems_none": "No poems yet.",
        "not_found_title": "Page not found",
        "not_found_home": "Go home",
    },
    "uz": {
        "nav_home": "Asosiy",
        "nav_blog": "Blog",
        "nav_essays": "Insholar",
        "nav_poems": "She'riyat",
        "nav_projects": "Loyihalar",
        "nav_books": "Kitoblar",
        "nav_tools": "Qurollar",
        "nav_now": "Hozir",
        "nav_about": "Haqida",
        "nav_contact": "Aloqa",
        "home_tagline": "Dasturchi. O'rganayotgan va qurayotgan ishlarim haqida yozaman.",
        "home_recent": "So'nggi insholar",
        "home_all_essays": "→ Barcha insholar",
        "home_explore": "Saytda",
        "home_contact_invite": "Muloqotga taklif qilaman.",
        "essays_title": "Insholar",
        "essays_tag_prefix": "Teg:",
        "essays_tag_clear": "tozalash",
        "essays_none": "Hali insholar yo'q.",
        "essays_none_tagged": "Ushbu teg bilan insholar yo'q:",
        "about_title": "Haqida",
        "now_title": "Hozir",
        "contact_title": "Aloqa",
        "projects_title": "Loyihalar",
        "books_title": "Kitoblar",
        "books_reading": "Hozir o'qiyapman",
        "books_done": "O'qib bo'ldim",
        "books_want": "O'qimoqchi",
        "tools_title": "Qurollar",
        "post_back": "← Insholar",
        "post_back_blog": "← Blog",
        "post_back_poems": "← She'riyat",
        "poems_title": "She'riyat",
        "poems_none": "Hali she'rlar yo'q.",
        "not_found_title": "Sahifa topilmadi",
        "not_found_home": "Bosh sahifaga",
    },
    "uz_cyr": {
        "nav_home": "Асосий",
        "nav_blog": "Блог",
        "nav_essays": "Иншолар",
        "nav_poems": "Шеърият",
        "nav_projects": "Лойиҳалар",
        "nav_books": "Китоблар",
        "nav_tools": "Қуроллар",
        "nav_now": "Ҳозир",
        "nav_about": "Ҳақида",
        "nav_contact": "Алоқа",
        "home_tagline": "Дастурчи. Ўрганаётган ва қураётган ишларим ҳақида ёзаман.",
        "home_recent": "Сўнгги иншолар",
        "home_all_essays": "→ Барча иншолар",
        "home_explore": "Сайтда",
        "home_contact_invite": "Мулоқотга таклиф қиламан.",
        "essays_title": "Иншолар",
        "essays_tag_prefix": "Тег:",
        "essays_tag_clear": "тозалаш",
        "essays_none": "Ҳали иншолар йўқ.",
        "essays_none_tagged": "Ушбу тег билан иншолар йўқ:",
        "about_title": "Ҳақида",
        "now_title": "Ҳозир",
        "contact_title": "Алоқа",
        "projects_title": "Лойиҳалар",
        "books_title": "Китоблар",
        "books_reading": "Ҳозир ўқияпман",
        "books_done": "Ўқиб бўлдим",
        "books_want": "Ўқимоқчи",
        "tools_title": "Қуроллар",
        "post_back": "← Иншолар",
        "post_back_blog": "← Блог",
        "post_back_poems": "← Шеърият",
        "poems_title": "Шеърият",
        "poems_none": "Ҳали шеърлар йўқ.",
        "not_found_title": "Саҳифа топилмади",
        "not_found_home": "Бош саҳифага",
    },
}


def detect_lang() -> str:
    lang = request.cookies.get("lang")
    if lang in TRANSLATIONS:
        return lang
    accept = request.headers.get("Accept-Language", "").lower()
    for part in accept.split(","):
        tag = part.split(";")[0].strip()
        if tag.startswith("uz"):
            return "uz"
    return "en"


@app.context_processor
def inject_globals():
    lang = detect_lang()
    return {"t": TRANSLATIONS[lang], "lang": lang}


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
    exts = ["fenced_code", "tables", "footnotes"]
    if "poems" in path.parts:
        exts.append("nl2br")
    meta["content"] = markdown.markdown(body, extensions=exts)
    meta["slug"] = _derive_slug(path, meta)
    meta.setdefault("published", True)
    meta.setdefault("tags", [])
    return meta


_LANG_VARIANT = re.compile(r'\.(uz|uz_cyr)\.md$')


@lru_cache(maxsize=None)
def get_slug_map() -> dict:
    result = {}
    for p in (CONTENT / "posts").glob("*.md"):
        if _LANG_VARIANT.search(p.name):
            continue
        text = p.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            meta = yaml.safe_load(parts[1]) or {}
        else:
            meta = {}
        slug = _derive_slug(p, meta)
        result[slug] = p
    return result


@lru_cache(maxsize=None)
def get_posts(tag: str | None = None) -> list[dict]:
    paths = sorted(
        [p for p in (CONTENT / "posts").glob("*.md")
         if not _LANG_VARIANT.search(p.name)],
        key=lambda p: p.stem,
        reverse=True,
    )
    posts = [parse_post(p) for p in paths]
    posts = [p for p in posts if p.get("published")]
    if tag:
        posts = [p for p in posts if tag in p.get("tags", [])]
    return posts


@lru_cache(maxsize=None)
def get_blog_slug_map() -> dict:
    result = {}
    if not BLOG.exists():
        return result
    for p in BLOG.glob("*.md"):
        if _LANG_VARIANT.search(p.name):
            continue
        text = p.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            meta = yaml.safe_load(parts[1]) or {}
        else:
            meta = {}
        slug = _derive_slug(p, meta)
        result[slug] = p
    return result


@lru_cache(maxsize=None)
def get_blog_posts(tag: str | None = None) -> list[dict]:
    if not BLOG.exists():
        return []
    paths = sorted(
        [p for p in BLOG.glob("*.md") if not _LANG_VARIANT.search(p.name)],
        key=lambda p: p.stem,
        reverse=True,
    )
    posts = [parse_post(p) for p in paths]
    posts = [p for p in posts if p.get("published")]
    if tag:
        posts = [p for p in posts if tag in p.get("tags", [])]
    return posts


@lru_cache(maxsize=None)
def get_poems_slug_map() -> dict:
    result = {}
    if not POEMS.exists():
        return result
    for p in POEMS.glob("*.md"):
        if _LANG_VARIANT.search(p.name):
            continue
        text = p.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            meta = yaml.safe_load(parts[1]) or {}
        else:
            meta = {}
        slug = _derive_slug(p, meta)
        result[slug] = p
    return result


@lru_cache(maxsize=None)
def get_poems(tag: str | None = None) -> list[dict]:
    if not POEMS.exists():
        return []
    paths = sorted(
        [p for p in POEMS.glob("*.md") if not _LANG_VARIANT.search(p.name)],
        key=lambda p: p.stem,
        reverse=True,
    )
    posts = [parse_post(p) for p in paths]
    posts = [p for p in posts if p.get("published")]
    if tag:
        posts = [p for p in posts if tag in p.get("tags", [])]
    return posts


@lru_cache(maxsize=None)
def _lang_title(base_path_str: str, lang: str) -> str | None:
    base = Path(base_path_str)
    lang_path = base.parent / f"{base.stem}.{lang}.md"
    if not lang_path.exists():
        return None
    text = lang_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        meta = yaml.safe_load(text.split("---", 2)[1]) or {}
        return meta.get("title") or None
    return None


def localize_titles(posts: list[dict], lang: str, slug_map: dict) -> list[dict]:
    if lang == "en":
        return posts
    out = []
    for p in posts:
        base = slug_map.get(p["slug"])
        if base:
            title = _lang_title(str(base), lang)
            if title:
                p = {**p, "title": title}
        out.append(p)
    return out


@lru_cache(maxsize=None)
def _render_md(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        return ""
    return markdown.markdown(
        path.read_text(encoding="utf-8"),
        extensions=["fenced_code", "tables"],
    )


def read_md(filename: str, lang: str = "en") -> str:
    stem, ext = filename.rsplit(".", 1)
    lang_path = CONTENT / f"{stem}.{lang}.{ext}"
    if lang_path.exists():
        return _render_md(str(lang_path))
    return _render_md(str(CONTENT / filename))


@lru_cache(maxsize=None)
def read_yaml(filename: str):
    path = CONTENT / filename
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


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


@app.route("/lang/<code>")
def set_lang(code):
    if code not in TRANSLATIONS:
        code = "en"
    resp = redirect(request.referrer or "/")
    resp.set_cookie("lang", code, max_age=365 * 24 * 60 * 60, samesite="Lax")
    return resp


@app.route("/")
def home():
    return render_template("home.html", recent=get_posts()[:5])


@app.route("/blog")
def blog():
    tag = request.args.get("tag") or None
    lang = detect_lang()
    posts = localize_titles(get_blog_posts(tag), lang, get_blog_slug_map())
    return render_template("essays.html", posts=posts, active_tag=tag, base_url="/blog", page_title=TRANSLATIONS[lang]["nav_blog"])


@app.route("/blog/<slug>")
def blog_post(slug):
    path = get_blog_slug_map().get(slug)
    if path is None:
        abort(404)
    lang = detect_lang()
    lang_path = path.parent / f"{path.stem}.{lang}.md"
    return render_template(
        "post.html",
        post=parse_post(lang_path if lang_path.exists() else path),
        back_url="/blog",
        back_label="post_back_blog",
    )


@app.route("/essays")
def essays():
    tag = request.args.get("tag") or None
    lang = detect_lang()
    posts = localize_titles(get_posts(tag), lang, get_slug_map())
    return render_template("essays.html", posts=posts, active_tag=tag, base_url="/essays")


@app.route("/essays/<slug>")
def post(slug):
    path = get_slug_map().get(slug)
    if path is None:
        abort(404)
    lang = detect_lang()
    lang_path = path.parent / f"{path.stem}.{lang}.md"
    return render_template(
        "post.html",
        post=parse_post(lang_path if lang_path.exists() else path),
        back_url="/essays",
        back_label="post_back",
    )


@app.route("/poems")
def poems():
    lang = detect_lang()
    posts = localize_titles(get_poems(), lang, get_poems_slug_map())
    return render_template(
        "essays.html", posts=posts, active_tag=None,
        base_url="/poems",
        page_title=TRANSLATIONS[lang]["poems_title"],
    )


@app.route("/poems/<slug>")
def poem(slug):
    path = get_poems_slug_map().get(slug)
    if path is None:
        abort(404)
    lang = detect_lang()
    lang_path = path.parent / f"{path.stem}.{lang}.md"
    return render_template(
        "post.html",
        post=parse_post(lang_path if lang_path.exists() else path),
        back_url="/poems",
        back_label="post_back_poems",
        is_poem=True,
    )


@app.route("/about")
def about():
    lang = detect_lang()
    return render_template("page.html", title_key="about_title", content=read_md("about.md", lang))


@app.route("/now")
def now():
    lang = detect_lang()
    return render_template("page.html", title_key="now_title", content=read_md("now.md", lang))


@app.route("/contact")
def contact():
    lang = detect_lang()
    return render_template("page.html", title_key="contact_title", content=read_md("contact.md", lang))


@app.route("/projects")
def projects():
    return render_template("projects.html", projects=read_yaml("projects.yaml"))


@app.route("/books")
def books():
    data = read_yaml("books.yaml")
    reading = [b for b in data if b.get("status") == "reading"]
    done = [b for b in data if b.get("status") == "done"]
    want = [b for b in data if b.get("status") == "want"]
    return render_template("books.html", reading=reading, done=done, want=want)


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
    static_routes = ["/", "/essays", "/about", "/now", "/contact", "/projects", "/books", "/tools"]
    xml = render_template("sitemap.xml", posts=posts, static_routes=static_routes, base=base)
    return Response(xml, mimetype="application/xml")


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=False)
