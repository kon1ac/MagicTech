"""Скачивание фото товаров через Яндекс.Картинки по названию модели."""

from __future__ import annotations

import hashlib
import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

# предпочитаем магазины / официальные CDN, а не превью/иконки
PREFER_HOST = (
    'cdn.shopify.com', 'keychron.com', 'images.unsplash.com',  # unsplash last resort never used as query
    'dns-shop.ru', 'ir.ozone.ru', 'ozone.ru', 'wbbasket.ru', 'wildberries.ru',
    'aliexpress-media.com', 'regard.ru', 'm.media-amazon.com', 'amazon.com',
    '4frag.ru', 'doctorhead.ru', 'citilink.ru', 'mvideo.ru', 'cdn1.productnation',
    'static.tildacdn.com', 'ogo1.ru', 'hyperx.com', 'logitech.com', 'razer.com',
    'steelseriescdn.com', 'sony.com',
)

SKIP_HOST = (
    'yastatic.net', 'avatars.mds.yandex', 'mc.yandex', 'favicon',
    'logo', 'sprite', 'icon',
)


def _request(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'Referer': 'https://yandex.ru/',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def search_image_urls(query: str, limit: int = 12) -> list[str]:
    q = urllib.parse.quote(query)
    url = f'https://yandex.ru/images/search?text={q}&itype=jpg'
    html = _request(url).decode('utf-8', 'replace').replace('&quot;', '"').replace('&amp;', '&')
    hrefs = re.findall(r'"img_href":"(https://[^"]+)"', html)
    origins = re.findall(r'"origin":\{[^}]*?"url":"(https://[^"]+)"', html)
    ordered: list[str] = []
    seen: set[str] = set()
    for u in hrefs + origins:
        u = u.strip()
        if not u or u in seen:
            continue
        low = u.lower()
        if any(s in low for s in SKIP_HOST):
            continue
        if not any(low.endswith(ext) or f'.{ext}?' in low or f'.{ext}&' in low
                   for ext in ('jpg', 'jpeg', 'png', 'webp')):
            # regard/cacheimg и подобные без расширения — ок
            if 'cacheimg' not in low and 'thumb' not in low and 'multimedia' not in low:
                if 'cdn' not in low and 'images' not in low and 'upload' not in low:
                    continue
        seen.add(u)
        ordered.append(u)
    # приоритет знакомых хостов
    preferred, rest = [], []
    for u in ordered:
        host = urllib.parse.urlparse(u).netloc.lower()
        if any(p in host for p in PREFER_HOST):
            preferred.append(u)
        else:
            rest.append(u)
    return (preferred + rest)[:limit]


def download_as_jpeg(url: str, min_side: int = 280) -> bytes | None:
    try:
        data = _request(url, timeout=40)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(data) < 2500:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        return None
    w, h = img.size
    if min(w, h) < min_side:
        return None
    # студийный кроп в 4:3
    target_w, target_h = 900, 675
    src_ratio = w / h
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_w = int(h * dst_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / dst_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=90, optimize=True)
    return out.getvalue()


def fetch_product_photo(query: str, cache_dir: Path, sku: str,
                        pause: float = 0.35) -> tuple[bytes | None, str]:
    """Возвращает (jpeg_bytes, source_url_or_reason)."""
    items = fetch_product_gallery(
        query, cache_dir, sku, count=1, pause=pause)
    if not items:
        return None, 'no-image'
    return items[0]


def _norm_url(url: str) -> str:
    """Срез query/size-суффиксов, чтобы c1000 и оригинал считались одним кадром."""
    try:
        p = urllib.parse.urlsplit(url.strip())
        path = p.path
        # ozon/wb size folders
        path = re.sub(r'/c\d+/', '/', path)
        path = re.sub(r'/w\d+/', '/', path)
        return f'{p.scheme}://{p.netloc.lower()}{path}'.rstrip('/')
    except Exception:
        return url.strip()


def fetch_product_gallery(
    query: str,
    cache_dir: Path,
    sku: str,
    count: int = 3,
    pause: float = 0.35,
    skip_urls: set[str] | None = None,
    skip_hashes: set[str] | None = None,
    slot_offset: int = 0,
) -> list[tuple[bytes, str]]:
    """Несколько разных фото одной модели. slot_offset≥1 — только доп. кадры (_1, _2…)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    skip_urls = {_norm_url(u) for u in (skip_urls or ()) if u}
    skip_hashes = set(skip_hashes or ())
    out: list[tuple[bytes, str]] = []

    # кэш слотов: при offset>0 никогда не берём SKU.jpg (главное)
    for i in range(count):
        slot = slot_offset + i
        if slot_offset > 0 and slot == 0:
            continue
        suffix = '' if slot == 0 else f'_{slot}'
        cached = cache_dir / f'{sku}{suffix}.jpg'
        marker = cache_dir / f'{sku}{suffix}.src.txt'
        if cached.exists() and cached.stat().st_size > 3000:
            data = cached.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            src = marker.read_text(encoding='utf-8').strip() if marker.exists() else 'cache'
            nsrc = _norm_url(src) if src != 'cache' else src
            if digest in skip_hashes or nsrc in skip_urls:
                continue
            skip_hashes.add(digest)
            if nsrc and nsrc != 'cache':
                skip_urls.add(nsrc)
            out.append((data, src))
    if len(out) >= count:
        return out[:count]

    queries = [
        query,
        f'{query} фото',
        f'{query} обзор',
        f'{query} ракурс',
        f'{query} упаковка',
    ]
    urls: list[str] = []
    seen_u: set[str] = set(skip_urls)
    for q in queries:
        if len(urls) >= count * 8:
            break
        try:
            found = search_image_urls(q, limit=20)
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        time.sleep(pause)
        for u in found:
            nu = _norm_url(u)
            if nu in seen_u:
                continue
            seen_u.add(nu)
            urls.append(u)

    for url in urls:
        if len(out) >= count:
            break
        if _norm_url(url) in skip_urls:
            continue
        data = download_as_jpeg(url)
        if not data:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in skip_hashes:
            continue
        skip_hashes.add(digest)
        skip_urls.add(_norm_url(url))
        slot = max(slot_offset, 1) + len(out) if slot_offset > 0 else slot_offset + len(out)
        if slot_offset == 0 and len(out) == 0:
            slot = 0
        suffix = '' if slot == 0 else f'_{slot}'
        (cache_dir / f'{sku}{suffix}.jpg').write_bytes(data)
        (cache_dir / f'{sku}{suffix}.src.txt').write_text(url, encoding='utf-8')
        out.append((data, url))
    return out
