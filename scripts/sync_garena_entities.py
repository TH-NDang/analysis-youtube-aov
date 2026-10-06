#!/usr/bin/env python3
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://lienquan.garena.vn"
ACADEMY = f"{BASE}/hoc-vien/"


def slugify(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def fetch(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; analysis-youtube-aov/1.0; +https://github.com/TH-NDang/analysis-youtube-aov)"
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def discover_hero_links(html: str):
    soup = BeautifulSoup(html, "html.parser")
    links = {}
    for a in soup.select("a[href*='/hoc-vien/tuong-skin/d/']"):
        href = a.get("href")
        if not href:
            continue
        url = urljoin(BASE, href)
        text = " ".join(a.stripped_strings).strip()
        key = url.rstrip("/").split("/")[-1]
        links[key] = {"url": url, "anchor_text": text}
    return list(links.values())


def parse_hero_page(url: str):
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    heading = None
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = " ".join(tag.stripped_strings).strip()
        if text and len(text) <= 60 and text.lower() not in {"gameplay", "trang phục", "kỹ năng"}:
            heading = text
            break

    if not heading:
        heading = url.rstrip("/").split("/")[-1].replace("-", " ").title()

    skins = []
    seen = set()
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if not alt:
            continue
        candidate = alt
        if candidate.lower().startswith("image "):
            candidate = candidate[6:].strip()
        if candidate.lower().startswith(heading.lower() + " "):
            skin_name = candidate[len(heading):].strip()
            if skin_name and skin_name.lower() not in {"avatar", "image"}:
                key = skin_name.casefold()
                if key not in seen:
                    seen.add(key)
                    skins.append({
                        "name": skin_name,
                        "hero": heading,
                        "source_url": url,
                    })

    return {
        "name": heading,
        "slug": slugify(heading),
        "source_url": url,
        "skins": skins,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fallback-heroes", default="config/heroes.json")
    ap.add_argument("--output-dir", default="data/entities")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fallback = json.loads(Path(args.fallback_heroes).read_text(encoding="utf-8"))
    fallback_names = fallback.get("heroes", [])

    try:
        academy_html = fetch(ACADEMY)
        links = discover_hero_links(academy_html)
    except Exception as exc:
        print(f"WARNING: cannot load academy page: {exc}")
        links = []

    hero_rows = []
    if links:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(parse_hero_page, row["url"]): row for row in links}
            for fut in as_completed(futures):
                try:
                    hero_rows.append(fut.result())
                except Exception as exc:
                    print(f"WARNING: hero page failed: {exc}")
    else:
        hero_rows = [
            {
                "name": name,
                "slug": slugify(name),
                "source_url": None,
                "skins": [],
            }
            for name in fallback_names
        ]

    by_name = {row["name"].casefold(): row for row in hero_rows}
    for name in fallback_names:
        if name.casefold() not in by_name:
            row = {
                "name": name,
                "slug": slugify(name),
                "source_url": None,
                "skins": [],
            }
            hero_rows.append(row)
            by_name[name.casefold()] = row

    hero_rows.sort(key=lambda x: x["name"].casefold())
    skins = []
    for row in hero_rows:
        skins.extend(row.pop("skins", []))

    (out / "heroes.json").write_text(
        json.dumps(
            {
                "source": ACADEMY,
                "count": len(hero_rows),
                "heroes": hero_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out / "skins.json").write_text(
        json.dumps(
            {
                "source": ACADEMY,
                "count": len(skins),
                "skins": sorted(skins, key=lambda x: (x["hero"].casefold(), x["name"].casefold())),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(json.dumps({"heroes": len(hero_rows), "skins": len(skins)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
