"""Kısa vadede yükseliş olasılığı — ve o olasılığın gerçekten bilgi taşıyıp taşımadığı.

Bir olasılık tahmininin iyiliği iki soruyla ölçülür:
  1. **Kalibrasyon** — "%60" dediği günlerin gerçekten %60'ında yükseldi mi?
  2. **Çözünürlük** — taban orandan (her gün aynı sayıyı söylemekten) farklı mı?

İkisini birden özetleyen ölçüt Brier skoru: ortalama (olasılık − gerçek)². Düşük iyi.
Karşılaştırma çıtası taban oran: "her gün %62 yükselir" diyen sabit tahmin. Model
bunu geçemiyorsa ürettiği olasılık, geçmiş yükseliş oranını tekrar etmekten ibarettir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config as C
from . import features as F

REFIT = 40


def _pipe():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=1000))


def run(df: pd.DataFrame, groups: dict[str, list[str]], horizon: int) -> dict:
    """h gün içinde yükseliş olasılığı + kalibrasyon karnesi."""
    cols = F.feature_cols(groups, [F.PRICE])
    tgt = f"y_{horizon}"
    if tgt not in df:
        df = df.copy()
        df[tgt] = np.log(df["price"].shift(-horizon) / df["price"])

    d = df.dropna(subset=cols + [tgt])
    if len(d) < C.MIN_TRAIN + horizon + 50:
        return {"error": "Yeterli veri yok."}

    X = d[cols].to_numpy(float)
    up = (d[tgt].to_numpy(float) > 0).astype(int)
    n = len(d)

    p = np.full(n, np.nan)
    est = None
    for i in range(C.MIN_TRAIN, n):
        cut = i - horizon
        if cut < C.MIN_TRAIN // 2:
            continue
        if (i - C.MIN_TRAIN) % REFIT == 0 or est is None:
            if len(np.unique(up[:cut])) < 2:
                continue
            est = _pipe().fit(X[:cut], up[:cut])
        p[i] = est.predict_proba(X[i:i + 1])[0, 1]

    m = ~np.isnan(p)
    pm, um = p[m], up[m]
    base = float(um.mean())

    brier = float(np.mean((pm - um) ** 2))
    brier_base = float(np.mean((base - um) ** 2))
    skill = 1 - brier / brier_base if brier_base > 0 else 0.0  # >0 ise taban orandan iyi

    # Kalibrasyon: tahmini dilimlere ayır, her dilimde gerçekleşme oranına bak
    bins = np.linspace(0, 1, 6)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = (pm >= lo) & (pm < hi)
        if sel.sum() >= 20:
            rows.append({
                "tahmin aralığı": f"%{lo*100:.0f}–{hi*100:.0f}",
                "söylediği": round(float(pm[sel].mean()) * 100, 1),
                "gerçekleşen": round(float(um[sel].mean()) * 100, 1),
                "gün": int(sel.sum()),
            })

    # Bugün için olasılık: tüm veriyle eğit, hedefi olmayan son satırı kullan
    est = _pipe().fit(X, up)
    live = df.dropna(subset=cols).iloc[-1]
    p_now = float(est.predict_proba(live[cols].to_numpy(float).reshape(1, -1))[0, 1])

    return {
        "p_up": p_now,
        "base_rate": base * 100,
        "brier": brier,
        "brier_base": brier_base,
        "skill": skill,
        "informative": bool(skill > 0.01),
        "calibration": pd.DataFrame(rows),
        "n": int(m.sum()),
        "horizon": horizon,
    }


def run_all(df: pd.DataFrame, groups: dict[str, list[str]],
            horizons: tuple[int, ...] = (2, 3)) -> dict[int, dict]:
    return {h: run(df, groups, h) for h in horizons}
