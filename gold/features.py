"""Özellik üretimi.

Bütün özellikler durağan (stationary) — ham fiyat seviyesi asla doğrudan özellik değil,
çünkü trendli bir seri modeli yanıltır. Getiri, oran ve z-skoru kullanılıyor.

Özellikler üç gruba ayrılıyor; `model.ablation()` bu grupları açıp kapatarak
"piyasa ve haber verisi eklemek gerçekten işe yaradı mı" sorusunu ölçüyor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

PRICE = "price"    # altın + dolar/TL kendi geçmişi
MARKET = "market"  # DXY, faiz, VIX, petrol, S&P
NEWS = "news"      # EPU, GDELT haber tonu


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def _logret(s: pd.Series, n: int = 1) -> pd.Series:
    """n günlük log getiri. Pozitif olmayan değerler maskelenir —
    CL=F (petrol) Nisan 2020'de negatife düştü, ham log NaN üretiyor."""
    return np.log(s.where(s > 0)).diff(n)


def _z(s: pd.Series, n: int = 252) -> pd.Series:
    """Yuvarlanan z-skoru — trendli seviyeleri durağanlaştırır."""
    m = s.rolling(n, min_periods=n // 4).mean()
    sd = s.rolling(n, min_periods=n // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def build(bundle: dict) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Özellik matrisi + hedefleri üretir.

    Döner: (df, gruplar) — df içinde `y_1`, `y_7`, `y_30` hedef sütunları da var.
    """
    gram: pd.Series = bundle["gram"]
    px: pd.DataFrame = bundle["prices"]
    idx = gram.index

    f = pd.DataFrame(index=idx)
    groups: dict[str, list[str]] = {PRICE: [], MARKET: [], NEWS: []}

    def add(name: str, series: pd.Series, group: str) -> None:
        f[name] = series.reindex(idx)
        groups[group].append(name)

    # --- Grup 1: fiyatın kendi geçmişi ------------------------------------
    lr = np.log(gram).diff()
    for k in (1, 2, 3, 5, 10):
        add(f"ret_{k}", lr.shift(k - 1) if k == 1 else lr.rolling(k).sum(), PRICE)
    for k in (5, 10, 20):
        add(f"vol_{k}", lr.rolling(k).std(), PRICE)
    for k in (5, 20, 50):
        add(f"sma_{k}", gram / gram.rolling(k).mean() - 1, PRICE)
    add("rsi_14", _rsi(gram) / 100 - 0.5, PRICE)

    # Sürükleyicileri ayrı tutuyoruz: TL değer kaybı ile küresel altın talebi
    # farklı hikâyeler, model ikisini ayrı öğrenmeli.
    usdtry_lr = np.log(px["usdtry"]).diff()
    ons_lr = np.log(px["ons"]).diff()
    for k in (1, 5, 10):
        add(f"usdtry_{k}", usdtry_lr.rolling(k).sum(), PRICE)
        add(f"ons_{k}", ons_lr.rolling(k).sum(), PRICE)

    # --- Grup 2: piyasa göstergeleri --------------------------------------
    mk: pd.DataFrame = bundle.get("market", pd.DataFrame())
    if not mk.empty:
        mk = mk.reindex(idx).ffill()
        for col in ("dxy", "oil", "spx"):
            if col in mk:
                for k in (1, 5):
                    add(f"{col}_{k}", _logret(mk[col], k), MARKET)
        if "tnx" in mk:
            # Faiz seviyesi trendli → ham seviye değil, değişim + z-skoru
            add("tnx_chg1", mk["tnx"].diff(), MARKET)
            add("tnx_chg5", mk["tnx"].diff(5), MARKET)
            add("tnx_z", _z(mk["tnx"]), MARKET)
        if "vix" in mk:
            # VIX ortalamaya dönen bir seri, seviyesi de anlamlı
            add("vix_lvl", _z(mk["vix"]), MARKET)
            add("vix_chg", _logret(mk["vix"]), MARKET)

    # --- Grup 3: haber tabanlı endeksler ----------------------------------
    epu: pd.Series = bundle.get("epu", pd.Series(dtype=float))
    if len(epu):
        e = epu.reindex(idx).ffill()
        add("epu_z", _z(e), NEWS)
        add("epu_chg1", e.pct_change(), NEWS)
        add("epu_chg5", e.pct_change(5), NEWS)

    gd: pd.Series = bundle.get("gdelt", pd.Series(dtype=float))
    if len(gd):
        g = gd.reindex(idx).ffill()
        add("tone", g, NEWS)
        add("tone_chg1", g.diff(), NEWS)
        add("tone_chg5", g.diff(5), NEWS)
        add("tone_dev30", g - g.rolling(30, min_periods=10).mean(), NEWS)

    # --- Takvim ------------------------------------------------------------
    for d in range(5):
        add(f"dow_{d}", pd.Series((idx.dayofweek == d).astype(float), index=idx), PRICE)

    # --- Hedefler: h gün sonraki log getiri --------------------------------
    for h in C.HORIZONS:
        f[f"y_{h}"] = np.log(gram.shift(-h) / gram)

    f["price"] = gram
    return f, groups


def feature_cols(groups: dict[str, list[str]], use: list[str]) -> list[str]:
    """Seçilen gruplardaki özellik adları."""
    return [c for g in use for c in groups.get(g, [])]
