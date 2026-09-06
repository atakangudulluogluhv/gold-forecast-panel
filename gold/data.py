"""Veri çekimi: Yahoo fiyatları, piyasa göstergeleri, EPU, GDELT, canlı TL fiyatı.

Her kaynak diske cache'lenir. Ağ hatasında cache'e düşülür — uygulama çökmez.
"""

from __future__ import annotations

import io
import time
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import requests

from . import config as C

# Kullanıcıya gösterilecek uyarılar (arayüz bunu okur)
WARNINGS: list[str] = []


def _warn(msg: str) -> None:
    if msg not in WARNINGS:
        WARNINGS.append(msg)


def _fresh(path, ttl: int = C.CACHE_TTL_SEC) -> bool:
    """Cache dosyası ttl saniyeden yeni mi?"""
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl


def _read_cached_series(path, name: str) -> pd.Series | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[name] if name in df.columns else None


# --------------------------------------------------------------------------- #
# Yahoo Finance
# --------------------------------------------------------------------------- #
def fetch_yahoo(symbol: str, rng: str = C.HISTORY_RANGE) -> pd.Series:
    """Bir sembolün günlük kapanış serisini döndürür.

    `^VIX` gibi semboller URL'de encode edilmeli; User-Agent zorunlu.
    """
    url = C.YAHOO_CHART.format(sym=urllib.parse.quote(symbol, safe=""))
    r = requests.get(url, headers=C.UA, params={"range": rng, "interval": "1d"}, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    s = pd.Series(
        res["indicators"]["quote"][0]["close"],
        index=pd.to_datetime(res["timestamp"], unit="s").normalize(),
        name=symbol,
    )
    return s[~s.index.duplicated(keep="last")].dropna()


def fetch_prices(force: bool = False) -> pd.DataFrame:
    """Altın (USD/ons) ve USDTRY serilerini `ons` / `usdtry` sütunlarıyla döndürür."""
    if not force and _fresh(C.F_PRICES):
        return pd.read_csv(C.F_PRICES, index_col=0, parse_dates=True)
    try:
        gold = fetch_yahoo(C.GOLD_SYM)
        usdtry = fetch_yahoo(C.USDTRY_SYM)
        df = pd.concat([gold.rename("ons"), usdtry.rename("usdtry")], axis=1).ffill().dropna()
        df.to_csv(C.F_PRICES)
        return df
    except Exception as e:  # ağ hatası → cache
        _warn(f"Fiyat verisi çekilemedi ({type(e).__name__}), önbellek kullanılıyor.")
        if C.F_PRICES.exists():
            return pd.read_csv(C.F_PRICES, index_col=0, parse_dates=True)
        raise


def fetch_market(force: bool = False) -> pd.DataFrame:
    """DXY / 10y faiz / VIX / petrol / S&P — tek DataFrame.

    Kaynakların gün sayıları farklı (2513–3038), bu yüzden birleştirip ffill ediyoruz.
    """
    if not force and _fresh(C.F_MARKET):
        return pd.read_csv(C.F_MARKET, index_col=0, parse_dates=True)
    cols = {}
    for sym, name in C.MARKET_SYMS.items():
        try:
            cols[name] = fetch_yahoo(sym)
        except Exception:
            _warn(f"{sym} göstergesi çekilemedi, o özellik atlanacak.")
    if not cols:
        if C.F_MARKET.exists():
            return pd.read_csv(C.F_MARKET, index_col=0, parse_dates=True)
        return pd.DataFrame()
    df = pd.concat(cols.values(), axis=1)
    df.columns = list(cols.keys())
    df = df.sort_index().ffill()
    df.to_csv(C.F_MARKET)
    return df


# --------------------------------------------------------------------------- #
# EPU — gazete tabanlı günlük belirsizlik endeksi (1985'ten beri)
# --------------------------------------------------------------------------- #
def fetch_epu(force: bool = False) -> pd.Series:
    """Günlük Economic Policy Uncertainty endeksi.

    CSV'de tarih üç ayrı sütunda geliyor: day, month, year.
    """
    if not force and _fresh(C.F_EPU, ttl=86400):
        s = _read_cached_series(C.F_EPU, "epu")
        if s is not None:
            return s
    try:
        r = requests.get(C.EPU_URL, headers=C.UA, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower() for c in df.columns]
        val_col = [c for c in df.columns if "index" in c][0]
        df = df.dropna(subset=["day", "month", "year", val_col])
        idx = pd.to_datetime(
            dict(year=df["year"].astype(int), month=df["month"].astype(int), day=df["day"].astype(int)),
            errors="coerce",
        )
        s = pd.Series(df[val_col].astype(float).values, index=idx, name="epu").dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        s.to_frame().to_csv(C.F_EPU)
        return s
    except Exception as e:
        _warn(f"EPU endeksi çekilemedi ({type(e).__name__}), önbellek kullanılıyor.")
        s = _read_cached_series(C.F_EPU, "epu")
        return s if s is not None else pd.Series(dtype=float, name="epu")


# --------------------------------------------------------------------------- #
# GDELT — haberlerin günlük duygu tonu (2017'den beri)
# --------------------------------------------------------------------------- #
def _gdelt_call(mode: str, start: datetime, end: datetime) -> pd.Series:
    """Tek GDELT isteği. 429 çok sık geldiği için üstel backoff'lu 3 deneme."""
    params = {
        "query": C.GDELT_QUERY,
        "mode": mode,
        "format": "json",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    delay = 15
    last = None
    for attempt in range(3):
        try:
            r = requests.get(C.GDELT_URL, headers=C.UA, params=params, timeout=90)
            if r.status_code == 429:
                raise requests.HTTPError("429 rate limit")
            r.raise_for_status()
            data = r.json().get("timeline", [])
            if not data:
                return pd.Series(dtype=float)
            rows = data[0]["data"]
            idx = pd.to_datetime([x["date"] for x in rows], format="%Y%m%dT%H%M%SZ").normalize()
            return pd.Series([float(x["value"]) for x in rows], index=idx).sort_index()
        except Exception as e:
            last = e
            if attempt < 2:
                time.sleep(delay)
                delay *= 2
    raise last  # type: ignore[misc]


def fetch_gdelt(force: bool = False) -> pd.Series:
    """Günlük haber tonu serisi. Artımlı: tam geçmiş bir kez, sonra eksik günler."""
    cached = _read_cached_series(C.F_GDELT, "tone")
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if cached is not None and not force:
        last = cached.index.max()
        if (today - last.to_pydatetime()).days < 1:
            return cached  # güncel, ağa hiç çıkma
        start = last.to_pydatetime()
    else:
        start = today - timedelta(days=365 * 8)  # GDELT 2017'de başlıyor

    try:
        fresh = _gdelt_call("timelinetone", start, today)
    except Exception as e:
        _warn(f"GDELT haber tonu çekilemedi ({type(e).__name__}), önbellek kullanılıyor.")
        return cached if cached is not None else pd.Series(dtype=float, name="tone")

    s = fresh if cached is None else pd.concat([cached, fresh])
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.name = "tone"
    s.to_frame().to_csv(C.F_GDELT)
    return s


# --------------------------------------------------------------------------- #
# truncgil — canlı Türkiye altın/döviz fiyatları
# --------------------------------------------------------------------------- #
def _tr_float(v: str) -> float:
    """'6.199,69' / '$4.056,90' / '%-0,92' → float"""
    return float(str(v).replace("$", "").replace("%", "").strip().replace(".", "").replace(",", "."))


def fetch_truncgil() -> dict:
    """Canlı gram altın, ons ve USD. Başarısızsa boş sözlük."""
    try:
        r = requests.get(C.TRUNCGIL_URL, headers=C.UA, timeout=20)
        r.encoding = "utf-8"  # yoksa Türkçe karakterler bozuluyor
        r.raise_for_status()
        d = r.json()
        out = {}
        for key, name in [("gram-altin", "gram"), ("ons", "ons"), ("USD", "usd")]:
            if key in d:
                out[name] = _tr_float(d[key]["Satış"])
                out[f"{name}_chg"] = _tr_float(d[key]["Değişim"])
        out["updated"] = d.get("Update_Date", "")
        return out
    except Exception as e:
        _warn(f"Canlı fiyat alınamadı ({type(e).__name__}); seri kalibre edilmedi.")
        return {}


# --------------------------------------------------------------------------- #
# Gram altın TL serisi
# --------------------------------------------------------------------------- #
def build_gram_series(force: bool = False) -> tuple[pd.Series, float, float | None]:
    """Gram altın TL geçmiş serisi.

    sentetik = ons_USD / 31.1034768 * USDTRY
    GC=F vadeli olduğu için spot'a göre ~%1.4 prim taşıyor; canlı gram fiyatına
    tek çarpanla kalibre ediyoruz. Modelleme getiri tabanlı olduğu için bu çarpan
    tahmini etkilemez, sadece seviyeyi piyasaya oturtur.

    Döner: (seri, ölçek_çarpanı, canlı_fiyat)
    """
    px = fetch_prices(force)
    synthetic = (px["ons"] / C.TROY_OUNCE_G * px["usdtry"]).rename("gram")

    live = fetch_truncgil()
    live_gram = live.get("gram")
    scale = (live_gram / synthetic.iloc[-1]) if live_gram else 1.0
    return synthetic * scale, float(scale), live_gram


def load_all(force: bool = False) -> dict:
    """Arayüzün ihtiyacı olan her şeyi tek çağrıda toplar."""
    WARNINGS.clear()
    gram, scale, live_gram = build_gram_series(force)
    px = fetch_prices(force)
    return {
        "gram": gram,
        "scale": scale,
        "live_gram": live_gram,
        "prices": px,
        "market": fetch_market(force),
        "epu": fetch_epu(force),
        "gdelt": fetch_gdelt(force),
        "live": fetch_truncgil(),
        "warnings": list(WARNINGS),
    }
