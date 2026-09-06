"""RSS başlıklarını çeker ve temizler.

Sadece başlık alınıyor — haber gövdesi asla. Token maliyeti orada patlıyor ve
duygu skoru için başlık yeterli bilgi taşıyor.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import config as C

MAX_HEADLINES = 20
MAX_LEN = 120

# Türkçe sorgu, çevrilmiş Vietnam altın haberlerini de yakalayabiliyor —
# TL/ons piyasasıyla ilgisi olmayan bu başlıkları eliyoruz.
NOISE = re.compile(r"\b(VND|SJC|rupee|PNJ|dong)\b", re.IGNORECASE)


def _clean(title: str) -> str:
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(r"\s+-\s+[^-]{2,40}$", "", t)  # Google News " - Kaynak" ekini at
    return t[:MAX_LEN]


def _key(title: str) -> str:
    """Kaba benzerlik anahtarı — aynı haberin farklı sitelerdeki kopyalarını eler."""
    words = re.findall(r"\w+", title.lower())
    return " ".join(sorted(words)[:6])


def fetch_headlines(limit: int = MAX_HEADLINES) -> list[str]:
    """Son 48 saatin tekilleştirilmiş başlıkları. Ağ hatasında boş liste."""
    try:
        import feedparser
    except ImportError:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    seen: set[str] = set()
    out: list[tuple[datetime, str]] = []

    for url in C.RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers=C.UA)
        except Exception:
            continue
        for e in getattr(feed, "entries", []):
            title = _clean(getattr(e, "title", ""))
            if len(title) < 15 or NOISE.search(title):
                continue
            k = _key(title)
            if k in seen:
                continue
            when = cutoff
            if getattr(e, "published_parsed", None):
                try:
                    when = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            if when < cutoff:
                continue
            seen.add(k)
            out.append((when, title))

    out.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in out[:limit]]
