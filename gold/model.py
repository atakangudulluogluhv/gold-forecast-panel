"""Model eğitimi, walk-forward backtest, ablasyon ve tahmin.

Temel ilke: hiçbir sayıya, geçmişte test edilmeden güvenilmiyor. Her tahmin
"fiyat hiç değişmez" (naive) varsayımıyla karşılaştırılıyor; model bunu geçemiyorsa
arayüz bunu açıkça söylüyor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config as C
from . import features as F

# "trend" = geçmiş ortalama getiriyi tahmin et. Yönü hep yukarı çıkar, çünkü
# altın/TL uzun vadede yükselmiş. Bu satır olmadan modelin yön isabeti olduğundan
# çok daha iyi görünüyor: %72 yön isabeti, seri zaten %72 yükselmişse beceri değil.
MODEL_NAMES = ["naive", "trend", "drift", "ridge", "gbm"]


def _make(name: str):
    if name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    if name == "gbm":
        return HistGradientBoostingRegressor(
            max_depth=3, max_iter=200, learning_rate=0.05,
            min_samples_leaf=40, l2_regularization=1.0, random_state=0,
        )
    return None  # naive / drift kapalı form, fit gerekmiyor


def _clean(df: pd.DataFrame, cols: list[str], h: int) -> pd.DataFrame:
    """Özellik + hedef NaN'lerini at. Hedefin son h satırı zaten NaN (geleceğe bakıyor)."""
    return df.dropna(subset=cols + [f"y_{h}"])


def backtest(
    df: pd.DataFrame,
    groups: dict[str, list[str]],
    horizon: int,
    use_groups: list[str] | None = None,
    refit_every: int = C.REFIT_EVERY,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Genişleyen pencereli walk-forward test.

    Sızıntı önleme: t anında tahmin yaparken sadece t-h'ye kadarki satırlarla eğitiyoruz,
    çünkü y[t-h] ancak t anında öğrenilebilir. Aradaki h günlük boşluk (embargo) şart —
    olmazsa model cevabı görmüş olur ve backtest gerçekdışı iyi çıkar.

    Döner: (metrik tablosu, model adı → artıklar)
    """
    use_groups = use_groups or [F.PRICE, F.MARKET, F.NEWS]
    cols = F.feature_cols(groups, use_groups)
    d = _clean(df, cols, horizon)
    if len(d) < C.MIN_TRAIN + horizon + 50:
        return pd.DataFrame(), {}, {}

    X = d[cols].to_numpy(dtype=float)
    y = d[f"y_{horizon}"].to_numpy(dtype=float)
    price = d["price"].to_numpy(dtype=float)
    daily = d["ret_1"].to_numpy(dtype=float)
    n = len(d)

    preds = {m: np.full(n, np.nan) for m in MODEL_NAMES}
    fitted: dict[str, object] = {}

    for i in range(C.MIN_TRAIN, n):
        cut = i - horizon  # embargo
        if cut < C.MIN_TRAIN // 2:
            continue

        preds["naive"][i] = 0.0
        preds["trend"][i] = np.nanmean(y[:cut])          # geçmiş ortalama getiri
        preds["drift"][i] = np.nanmean(daily[max(0, cut - 60):cut]) * horizon

        if (i - C.MIN_TRAIN) % refit_every == 0 or "ridge" not in fitted:
            for m in ("ridge", "gbm"):
                est = _make(m)
                est.fit(X[:cut], y[:cut])
                fitted[m] = est
        for m in ("ridge", "gbm"):
            preds[m][i] = fitted[m].predict(X[i:i + 1])[0]

    mask = ~np.isnan(preds["naive"])
    rows, resid = [], {}
    actual_price = price * np.exp(y)

    for m in MODEL_NAMES:
        p = preds[m][mask]
        a = y[mask]
        pp = price[mask] * np.exp(p)
        ap = actual_price[mask]
        err = ap - pp
        resid[m] = p - a
        # naive her zaman 0 tahmin ettiği için yön isabeti tanımsız — NaN bırakıyoruz
        direction = np.nan if m == "naive" else float(np.mean(np.sign(p) == np.sign(a)) * 100)
        rows.append({
            "model": m,
            "MAE_TL": float(np.mean(np.abs(err))),
            "MAPE_%": float(np.mean(np.abs(err) / ap) * 100),
            "Yon_%": direction,
            "n": int(mask.sum()),
        })

    sim = {
        "preds": {m: preds[m][mask] for m in MODEL_NAMES},
        "y": y[mask],
        "price": price[mask],
        "up_rate": float((y[mask] > 0).mean() * 100),  # "hep yükselir" isabeti
    }
    return pd.DataFrame(rows).set_index("model"), resid, sim


def bootstrap_gap(resid_a: np.ndarray, resid_b: np.ndarray, n: int = 2000) -> tuple[float, float, float]:
    """|hata_a| - |hata_b| farkının ortalaması ve %95 aralığı.

    Aralık sıfırı içeriyorsa fark gürültüdür — tabloda küçük bir MAPE farkı
    görüp "model daha iyi" demeden önce bakılması gereken şey bu.
    """
    k = min(len(resid_a), len(resid_b))
    d = np.abs(resid_a[:k]) - np.abs(resid_b[:k])
    rng = np.random.default_rng(0)
    boot = rng.choice(d, size=(n, k), replace=True).mean(axis=1)
    return float(d.mean()), float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


def coverage(sim: dict, resid: dict, model_name: str, warm: int = 250) -> dict:
    """Aralık gerçekten söylediği kadar kapsıyor mu?

    Nokta tahmini ve yön becerisi zayıf olsa bile aralık dürüst olabilir — ve
    kullanıcı için asıl işe yarayan çıktı odur. Her gün, yalnızca o ana kadarki
    artıklardan bant kurulup gerçek değerin içine düşüp düşmediğine bakılıyor
    (geleceğe bakmadan). Hedef %80.
    """
    r, y, p = resid[model_name], sim["y"], sim["preds"][model_name]
    n = len(y)
    if n <= warm + 50:
        return {}

    hits, widths = [], []
    for i in range(warm, n):
        lo_i, hi_i = np.quantile(r[:i], 0.10), np.quantile(r[:i], 0.90)
        blo, bhi = p[i] - hi_i, p[i] - lo_i
        hits.append(blo <= y[i] <= bhi)
        widths.append((np.exp(bhi) - np.exp(blo)) * 100)

    cov = float(np.mean(hits) * 100)
    return {
        "coverage_%": cov,
        "target_%": 80.0,
        "width_%": float(np.mean(widths)),
        "n": len(hits),
        "verdict": ("dar" if cov < 75 else "geniş" if cov > 85 else "doğru"),
    }


def strategy_sim(sim: dict, model_name: str, horizon: int, cost_pct: float) -> dict:
    """'Model yükseliş derse altın tut, demezse TL'de kal' stratejisini al-tut ile karşılaştırır.

    Tahmin hatası düşük olması kâr demek değil — işlem yönle yapılır ve makas ödenir.
    Bu yüzden karar öncesi bakılacak asıl tablo burası.
    """
    p, y = sim["preds"][model_name], sim["y"]
    step = np.arange(0, len(y), horizon)          # çakışmayan pencereler
    sig = p[step] > 0
    real = y[step]
    switches = np.abs(np.diff(np.concatenate([[0], sig.astype(int)])))
    cost = cost_pct / 100.0
    strat = np.where(sig, real, 0.0) - switches * cost * 2
    return {
        "strateji_%": float(strat.sum() * 100),
        "al_tut_%": float(real.sum() * 100),
        "fark_%": float((strat.sum() - real.sum()) * 100),
        "islem": int(len(step)),
        "degisim": int(switches.sum()),
        "altinda_kalma_%": float(sig.mean() * 100),
    }


FEATURE_SETS = {
    "sadece fiyat": [F.PRICE],
    "+ piyasa": [F.PRICE, F.MARKET],
    "+ piyasa + haber": [F.PRICE, F.MARKET, F.NEWS],
}


def evaluate(df: pd.DataFrame, groups: dict[str, list[str]], horizon: int) -> dict:
    """Üç özellik setini de test edip en iyi (set, model) ikilisini seçer.

    Ablasyon burada hem dürüstlük aracı hem seçim aracı: özellik eklemek zarar
    veriyorsa o set seçilmiyor. Ölçüm 2200 gözlem üzerinde yapıldığı için fazla
    özellik aşırı öğrenmeye yol açabiliyor — tablo bunu görünür kılıyor.

    Not: hem özellik seti hem model aynı backtest üzerinde seçildiği için
    raporlanan MAPE hafif iyimser olabilir; arayüz bunu belirtiyor.
    """
    # Adil karşılaştırma için hepsi aynı pencerede: en dar veri seti neyse o.
    full = F.feature_cols(groups, [F.PRICE, F.MARKET, F.NEWS])
    sub = df.loc[_clean(df, full, horizon).index]

    tables, resids, sims, rows = {}, {}, {}, []
    for label, gs in FEATURE_SETS.items():
        tbl, res, sim = backtest(sub, groups, horizon, gs, refit_every=C.REFIT_EVERY * 2)
        if tbl.empty:
            continue
        tables[label], resids[label], sims[label] = tbl, res, sim
        # naive ve trend "çıta" satırları — aday değiller
        cand = tbl.drop(index=["naive", "trend"], errors="ignore")["MAPE_%"]
        rows.append({
            "özellik seti": label,
            "en iyi model": cand.idxmin(),
            "MAPE_%": round(float(cand.min()), 3),
            "Yön_%": round(float(tbl.loc[cand.idxmin(), "Yon_%"]), 1),
            "naive MAPE_%": round(float(tbl.loc["naive", "MAPE_%"]), 3),
        })

    ablation_tbl = pd.DataFrame(rows)
    if ablation_tbl.empty:
        return {}

    win = ablation_tbl.loc[ablation_tbl["MAPE_%"].idxmin()]
    best_set, best_model = str(win["özellik seti"]), str(win["en iyi model"])
    tbl, sim = tables[best_set], sims[best_set]
    naive_mape = float(tbl.loc["naive", "MAPE_%"])
    beats_naive = float(win["MAPE_%"]) < naive_mape

    if not beats_naive:
        best_model = "naive"

    # Fark gerçek mi gürültü mü — hem hata büyüklüğünde hem yön becerisinde
    gap, lo, hi = bootstrap_gap(resids[best_set]["naive"], resids[best_set][best_model])
    dir_model = tbl.loc[best_model, "Yon_%"]
    dir_edge = None if pd.isna(dir_model) else float(dir_model) - sim["up_rate"]

    return {
        "ablation": ablation_tbl,
        "backtest": tbl.round(3),
        "resid": resids[best_set],
        "sim": sim,
        "best_set": best_set,
        "best_model": best_model,
        "beats_naive": bool(beats_naive),
        "naive_mape": naive_mape,
        "best_mape": float(win["MAPE_%"]),
        "gap": gap, "gap_lo": lo, "gap_hi": hi,
        "gap_significant": bool(lo > 0),
        "up_rate": sim["up_rate"],
        "dir_edge": dir_edge,
        "coverage": coverage(sim, resids[best_set], best_model),
    }


def fit_predict(
    df: pd.DataFrame,
    groups: dict[str, list[str]],
    horizon: int,
    resid: dict[str, np.ndarray],
    best: str,
    use_groups: list[str],
) -> dict:
    """Tüm veriyle son modeli eğitip bugünden h gün sonrası için tahmin üretir."""
    cols = F.feature_cols(groups, use_groups)
    d = _clean(df, cols, horizon)
    X, y = d[cols].to_numpy(float), d[f"y_{horizon}"].to_numpy(float)

    live = df.dropna(subset=cols).iloc[-1]  # hedefi olmayan en son satır = bugün
    x_now = live[cols].to_numpy(float).reshape(1, -1)
    p_now = float(live["price"])

    if best == "naive":
        ret = 0.0
        est = None
    elif best == "drift":
        ret = float(df["ret_1"].tail(60).mean() * horizon)
        est = None
    else:
        est = _make(best)
        est.fit(X, y)
        ret = float(est.predict(x_now)[0])

    r = resid.get(best, np.array([0.0]))
    lo_r, hi_r = np.nanquantile(r, 0.10), np.nanquantile(r, 0.90)

    imp = []
    if est is not None:
        pi = permutation_importance(est, X[-500:], y[-500:], n_repeats=5, random_state=0)
        order = np.argsort(pi.importances_mean)[::-1][:8]
        imp = [(cols[i], float(pi.importances_mean[i])) for i in order]

    return {
        "ret": ret,
        "price": p_now * np.exp(ret),
        "lo": p_now * np.exp(ret - hi_r),
        "hi": p_now * np.exp(ret - lo_r),
        "last_price": p_now,
        "model": best,
        "importance": imp,
    }


def run(bundle: dict, horizon: int, df=None, groups=None) -> dict:
    """Bir ufuk için uçtan uca: özellik → ablasyon → model seçimi → tahmin."""
    if df is None:
        df, groups = F.build(bundle)

    ev = evaluate(df, groups, horizon)
    if not ev:
        return {"error": "Yeterli veri yok."}

    use = FEATURE_SETS[ev["best_set"]]
    pred = fit_predict(df, groups, horizon, ev["resid"], ev["best_model"], use)
    pred.update({k: v for k, v in ev.items() if k != "resid"})
    pred["horizon"] = horizon
    return pred


def run_cached(bundle: dict, horizon: int, force: bool = False) -> dict:
    """`run` ile aynı, ama sonucu diske yazar.

    Backtest ufuk başına ~45 sn sürüyor; arayüz her açılışta bunu tekrarlamamalı.
    Anahtar: (ufuk, verinin son tarihi) — veri değişince kendiliğinden tazeleniyor.
    """
    import joblib

    key = f"m{horizon}_{bundle['gram'].index[-1].date()}"
    store = {}
    if C.F_MODELS.exists() and not force:
        try:
            store = joblib.load(C.F_MODELS)
            if key in store:
                return store[key]
        except Exception:
            store = {}

    res = run(bundle, horizon)
    store = {k: v for k, v in store.items() if k.endswith(str(bundle["gram"].index[-1].date()))}
    store[key] = res
    try:
        joblib.dump(store, C.F_MODELS)
    except Exception:
        pass
    return res
