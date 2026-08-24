"""Normalise and store an uploaded image.

Shared by the web admin panel (app.py) and the Telegram bot (bot/bot.py) so that
a cover uploaded from either side gets identical treatment: proven to be an image,
stripped of metadata, and downscaled to something a distant reader can load.
"""
import io
import re
import secrets
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent   # /root/blog — the URL root for static files
IMAGES = ROOT / "static/img"
MAX_BYTES = 16 * 1024 * 1024
MAX_WIDTH = 1600
ALLOWED = {"JPEG", "PNG", "GIF", "WEBP"}


def _public_url(path: Path) -> str:
    """Public URL for a stored file, whether the caller passed a relative or absolute dir."""
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        rel = Path("static/img") / path.name
    return "/" + rel.as_posix()


def _slug(text: str) -> str:
    text = re.sub(r"[ʻʼʼ''‘’`]", "", (text or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def save_image_bytes(raw: bytes, hint: str = "image", images_dir: Path | None = None) -> str | None:
    """Store `raw` as an image and return its public URL, or None if it is not one.

    Nothing is taken on trust: Pillow parsing the bytes is what proves the upload is
    an image at all, re-saving is what drops EXIF (GPS included), and the filename is
    generated here rather than taken from the caller. Animated GIFs are written through
    unchanged, since re-encoding would flatten them to a single frame.
    """
    directory = images_dir or IMAGES
    if not raw or len(raw) > MAX_BYTES:
        return None
    try:
        Image.open(io.BytesIO(raw)).verify()   # structural check; consumes the buffer
        im = Image.open(io.BytesIO(raw))       # ...so reopen for the real work
        fmt = (im.format or "").upper()
    except Exception:
        return None
    if fmt not in ALLOWED:
        return None

    stem = _slug(Path(hint or "image").stem)[:40] or "image"
    name = f"{date.today().isoformat()}-{stem}-{secrets.token_hex(3)}"
    directory.mkdir(parents=True, exist_ok=True)

    if fmt == "GIF":
        out = directory / f"{name}.gif"
        out.write_bytes(raw)
        return _public_url(out)

    im = ImageOps.exif_transpose(im)            # honour camera rotation, then lose it
    if im.width > MAX_WIDTH:
        height = round(im.height * MAX_WIDTH / im.width)
        im = im.resize((MAX_WIDTH, height), Image.LANCZOS)

    if im.mode in {"RGBA", "LA"} or (im.mode == "P" and "transparency" in im.info):
        out = directory / f"{name}.png"
        im.convert("RGBA").save(out, "PNG", optimize=True)
    else:
        out = directory / f"{name}.jpg"
        im.convert("RGB").save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return _public_url(out)
