#!/usr/bin/env python3
import re
from pathlib import Path
from datetime import date, timedelta

POSTS = [
    ("Atrof-muhitga qarang",                        "https://t.me/xurshidblg/6"),
    ("Qiymat",                                       "https://t.me/xurshidblg/10"),
    ("Ishlab topilgan luqma",                        "https://t.me/xurshidblg/11"),
    ("Imtihon",                                      "https://t.me/xurshidblg/12"),
    ("O'zlik",                                       "https://t.me/xurshidblg/13"),
    ("So'z",                                         "https://t.me/xurshidblg/15"),
    ("ILM",                                          "https://t.me/xurshidblg/16"),
    ("Blog",                                         "https://t.me/xurshidblg/17"),
    ("Har bir kutilgan narsa yaqindir",              "https://t.me/xurshidblg/19"),
    ("Dushanbachilar",                               "https://t.me/xurshidblg/20"),
    ("Xos Bilim",                                    "https://t.me/xurshidblg/23"),
    ("Til o'rganish",                                "https://t.me/xurshidblg/25"),
    ("Aqliy Modellar Haqida",                        "https://t.me/xurshidblg/28"),
    ("O'rganuvchi bo'ling!",                         "https://t.me/xurshidblg/30"),
    ("Ramazon",                                      "https://t.me/xurshidblg/31"),
    ("Aqlli gaplar foyda bermaydi",                  "https://t.me/xurshidblg/32"),
    ("Sabr (qisqa muddatda)",                        "https://t.me/xurshidblg/34"),
    ("Sabr (uzoq muddatda)",                         "https://t.me/xurshidblg/36"),
    ("O'zimiz bilan",                                "https://t.me/xurshidblg/37"),
    ("Tartib",                                       "https://t.me/xurshidblg/40"),
    ("Baribir o'tib ketadi",                         "https://t.me/xurshidblg/41"),
    ("Ilm ulashing",                                 "https://t.me/xurshidblg/42"),
    ("Tekshirib ko'ring",                            "https://t.me/xurshidblg/43"),
    ("Tekshirib ko'ring (davomi)",                   "https://t.me/xurshidblg/44"),
    ("E'tibor",                                      "https://t.me/xurshidblg/45"),
    ("Hurmattalablik",                               "https://t.me/xurshidblg/49"),
    ("Sog'lik",                                      "https://t.me/xurshidblg/50"),
    ("Yozish haqida",                                "https://t.me/xurshidblg/51"),
    ("Sun'iy intellekt davrida qanday o'rganamiz?",  "https://t.me/xurshidblg/55"),
]


def slugify(text):
    text = text.lower()
    text = re.sub(r"['ʻʼ‘’`]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def main():
    blog_dir = Path(__file__).parent.parent / "content" / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    start = date(2025, 1, 6)
    for i, (title, tg_url) in enumerate(POSTS):
        post_date = start + timedelta(weeks=i)
        slug = slugify(title)
        fname = f"{post_date.isoformat()}-{slug}.md"
        path = blog_dir / fname
        if path.exists():
            print(f"Skip (exists): {fname}")
            continue
        content = (
            f"---\n"
            f"title: \"{title}\"\n"
            f"date: {post_date.isoformat()}\n"
            f"slug: {slug}\n"
            f"published: false\n"
            f"tags: []\n"
            f"---\n\n"
            f"*(Matn keyinroq qo'shiladi)*\n\n"
            f"[Telegramda o'qish]({tg_url})\n"
        )
        path.write_text(content, encoding="utf-8")
        print(f"Created: {fname}")

    print(f"\nDone — {len(POSTS)} posts processed.")


if __name__ == "__main__":
    main()
