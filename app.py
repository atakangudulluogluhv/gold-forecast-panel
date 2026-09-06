"""Altın/TL Tahmin Paneli — Streamlit arayüzü.

Çalıştırmak için:  streamlit run app.py
"""

from __future__ import annotations

import warnings

import streamlit as st
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

from gold import ai, data, features, model, news, proba  # noqa: E402
from gold import config as C  # noqa: E402
from gold.ui import caption, importance_chart, pct, price_chart, tl  # noqa: E402

st.set_page_config(page_title="Altın/TL Tahmin", page_icon="🥇", layout="wide")


# --------------------------------------------------------------------------- #
# Veri ve model — Streamlit her etkileşimde script'i baştan çalıştırdığı için
# bunlar cache'lenmezse her tıklamada ağa çıkılır ve model yeniden eğitilir.
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Veriler alınıyor…", ttl=3600)
def load_data(nonce: int = 0):
    b = data.load_all(force=nonce > 0)
    df, groups = features.build(b)
    return b, df, groups


@st.cache_resource(show_spinner="Model eğitiliyor (ilk çalıştırmada ~1 dk)…")
def load_model(horizon: int, stamp: str, nonce: int = 0):
    b, df, groups = load_data(st.session_state.get("data_nonce", 0))
    return model.run_cached(b, horizon, force=nonce > 0)


@st.cache_resource(show_spinner="Olasılık modeli eğitiliyor…")
def load_proba(stamp: str, nonce: int = 0):
    _, df_, groups_ = load_data(st.session_state.get("data_nonce", 0))
    return proba.run_all(df_, groups_, C.PROBA_HORIZONS)


@st.cache_data(show_spinner=False, ttl=3600)
def load_headlines(nonce: int = 0):
    return news.fetch_headlines()


# --------------------------------------------------------------------------- #
# Kenar çubuğu
# --------------------------------------------------------------------------- #
st.session_state.setdefault("data_nonce", 0)
st.session_state.setdefault("model_nonce", 0)

with st.sidebar:
    st.subheader("Ayarlar")
    horizon = st.radio("Tahmin ufku", C.HORIZONS, index=1,
                       format_func=lambda h: f"{h} gün", horizontal=True)
    window = st.select_slider("Grafikte gösterilecek geçmiş",
                              options=[90, 180, 365, 730, 1825],
                              value=365,
                              format_func=lambda d: f"{d} gün")
    st.divider()
    if st.button("Verileri yenile", width="stretch"):
        st.session_state.data_nonce += 1
        st.cache_data.clear()
    if st.button("Modeli yeniden eğit", width="stretch"):
        st.session_state.model_nonce += 1
        st.cache_resource.clear()
    st.divider()
    st.caption("Claude API anahtarı: " + ("✅ tanımlı" if ai.has_key() else "❌ yok"))
    if not ai.has_key():
        st.caption("`.env` dosyasına `ANTHROPIC_API_KEY=...` ekleyin.")


bundle, df, groups = load_data(st.session_state.data_nonce)
gram = bundle["gram"]
res = load_model(horizon, str(gram.index[-1].date()), st.session_state.model_nonce)

# --------------------------------------------------------------------------- #
# Başlık + "nasıl çalışıyor"
# --------------------------------------------------------------------------- #
st.title("🥇 Altın/TL Tahmin Paneli")
st.write("Gram altının TL fiyatını geçmiş verilerle tahmin eder ve tahminin ne kadar "
         "güvenilir olduğunu geçmişe dönük testle ölçer.")

with st.expander("Bu panel nasıl çalışıyor?"):
    st.markdown(
        """
1. **Veri** — Altın (USD/ons) ve dolar/TL fiyatları Yahoo Finance'ten, canlı gram altın
   fiyatı truncgil'den alınır. Gram altın TL = ons ÷ 31,1035 × dolar/TL.
2. **Özellik** — Ham fiyat yerine getiriler, oynaklık, RSI gibi durağan göstergeler
   üretilir. Ayrıca dolar endeksi, ABD faizi, VIX, petrol ve haber tabanlı endeksler
   (EPU, GDELT) hesaba katılır.
3. **Model** — Bilgisayarınızda çalışan bir regresyon modeli (scikit-learn) tahmini üretir.
   Hangi özellik setinin ve hangi modelin kullanılacağı, geçmişe dönük testte en iyi
   sonucu vereni seçilerek belirlenir.
4. **Yorum** — Claude **tahmini yapmaz**. Sadece yukarıdaki sayılara bakıp kısa bir
   Türkçe yorum yazar ve günlük haber başlıklarını puanlar.

**Neden böyle?** Bir dil modeline ham fiyat serisi verip "tahmin et" demek ölçülemez ve
her sorguda değişen bir sayı üretir. Regresyonun ise geçmişe dönük test edilebilir bir
başarısı vardır — panelde göreceğiniz tüm doğruluk rakamları o testten geliyor.
        """
    )

for w in bundle.get("warnings", []):
    st.warning(w, icon="⚠️")

if res.get("error"):
    st.error(res["error"])
    st.stop()

# --------------------------------------------------------------------------- #
# Özet metrikler
# --------------------------------------------------------------------------- #
live = bundle.get("live", {})
chg = res["price"] / res["last_price"] - 1

c1, c2, c3, c4 = st.columns(4)
c1.metric("Gram altın (canlı)", f"{tl(res['last_price'])} TL",
          pct(live.get("gram_chg")) if live.get("gram_chg") is not None else None)
c2.metric(f"{horizon} gün sonrası tahmini", f"{tl(res['price'])} TL", pct(chg * 100))
c3.metric("Olası aralık", f"{tl(res['lo'], 0)} – {tl(res['hi'], 0)} TL")
c4.metric("Kullanılan model", res["model"], res["best_set"], delta_color="off")

if res["beats_naive"] and res.get("gap_significant"):
    st.success(
        f"Model geçmiş testte 'fiyat değişmez' varsayımını geçiyor: "
        f"ortalama hata {pct(res['best_mape'])} — karşısında {pct(res['naive_mape'])}. "
        f"Fark istatistiksel olarak anlamlı.",
        icon="✅",
    )
elif res["beats_naive"]:
    st.info(
        f"Model 'fiyat değişmez' varsayımından biraz iyi ({pct(res['best_mape'])} vs "
        f"{pct(res['naive_mape'])}) ama fark istatistiksel olarak anlamsız — gürültü olabilir.",
        icon="ℹ️",
    )
else:
    st.warning(
        f"Bu vadede hiçbir model 'fiyat değişmez' varsayımını geçemedi "
        f"({pct(res['naive_mape'])} hata). Fiyat rastgele yürüyüşe çok yakın, bu yüzden "
        f"tahmin olarak bugünkü fiyat gösteriliyor.",
        icon="⚠️",
    )

# Yön becerisi — asıl karar bilgisi. Yön isabetini trend çıtasıyla birlikte göstermezsek
# rakam olduğundan çok daha iyi görünüyor.
if res.get("dir_edge") is not None:
    edge = res["dir_edge"]
    msg = (f"**Yön becerisi:** model {pct(res['backtest'].loc[res['model'], 'Yon_%'], 1)} "
           f"isabetle yön tutturuyor; ama seri geçmişte zaten "
           f"{pct(res['up_rate'], 1)} oranında yükselmiş. "
           f"Gerçek üstünlük: **{edge:+.1f} puan**.")
    (st.success if edge > 3 else st.error)(
        msg + ("" if edge > 3 else " Bu fark sıfıra yakın — modelin yön konusunda "
               "'hep yükselir' demekten fazlası yok."),
        icon="🧭",
    )

# --------------------------------------------------------------------------- #
# Ana grafik
# --------------------------------------------------------------------------- #
st.subheader("Fiyat ve tahmin")
hist = gram.tail(window)
st.plotly_chart(price_chart(hist, res, horizon), width="stretch",
                config={"displayModeBar": False})
cov = res.get("coverage") or {}
if cov:
    v = cov["coverage_%"]
    note = {"doğru": "Aralık dürüst — söylediği kadar kapsıyor.",
            "dar": "**Aralık olduğundan dar** — gerçek risk gösterilenden yüksek.",
            "geniş": "Aralık biraz geniş — model fazla temkinli."}[cov["verdict"]]
    (st.success if cov["verdict"] != "dar" else st.error)(
        f"**Aralığın güvenilirliği ölçüldü:** hedef %80'e karşılık gerçek kapsama "
        f"**{pct(v, 1)}** ({cov['n']} gün üzerinde, geleceğe bakmadan). "
        f"Ortalama genişlik ±{pct(cov['width_%'] / 2, 1)}. {note}",
        icon="🎯",
    )
caption("Kesikli çizgi tahmini, gölgeli alan olası aralığı gösterir. Aralık, geçmiş "
        "testteki hataların %10–%90 dilimine göre çizilir; yukarıdaki ölçüm bu bandın "
        "gerçekten söylediği oranda tutup tutmadığını sınar. Panelin en güvenilir "
        "çıktısı tek bir tahmin sayısı değil, bu aralıktır.")

# --------------------------------------------------------------------------- #
# Piyasa göstergeleri
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Kısa vadeli yükseliş olasılığı
# --------------------------------------------------------------------------- #
st.subheader("Kısa vadede yükseliş olasılığı")
pr = load_proba(str(gram.index[-1].date()), st.session_state.model_nonce)

pcols = st.columns(len(C.PROBA_HORIZONS) * 2)
for j, h in enumerate(C.PROBA_HORIZONS):
    q = pr.get(h, {})
    if q.get("error"):
        pcols[j * 2].info(q["error"])
        continue
    pcols[j * 2].metric(f"{h} gün içinde yükselir", pct(q["p_up"] * 100, 1))
    pcols[j * 2 + 1].metric(f"{h} gün taban oranı", pct(q["base_rate"], 1),
                            help="Geçmişte bu vadenin ne kadarı yükselişle bitmiş — "
                                 "aşılması gereken çıta bu.")

good = [h for h in C.PROBA_HORIZONS if pr.get(h, {}).get("informative")]
if good:
    st.success(f"Olasılık modeli {', '.join(f'{h} gün' for h in good)} vadesinde "
               f"taban orandan daha bilgili çıktı.", icon="✅")
else:
    st.error(
        "**Bu olasılıklar taban orandan daha bilgili değil.** Model, geçmişteki yükseliş "
        "oranını tekrar etmekten fazlasını yapmıyor — yani gösterdiği yüzde, bugüne dair "
        "bir bilgi taşımıyor. Karar verirken bu sayıya ağırlık vermeyin.",
        icon="🚫",
    )

with st.expander("Bu olasılık ne kadar güvenilir? (kalibrasyon karnesi)"):
    for h in C.PROBA_HORIZONS:
        q = pr.get(h, {})
        if q.get("error"):
            continue
        st.markdown(f"**{h} gün** — Brier skoru {q['brier']:.4f} · "
                    f"taban oran çıtası {q['brier_base']:.4f} · "
                    f"beceri {q['skill']:+.3f} ({q['n']} gün test edildi)")
        if not q["calibration"].empty:
            st.dataframe(q["calibration"], hide_index=True, width="stretch")
    caption("**Brier skoru** olasılık tahmininin hatası — düşük iyi. **Beceri** pozitifse "
            "model taban orandan iyidir, sıfır veya negatifse değildir. Kalibrasyon "
            "tablosunda 'söylediği' ile 'gerçekleşen' sütunları birbirine yakınsa "
            "olasılıklar dürüsttür; uzaksa model kendine olduğundan fazla güveniyordur.")

st.subheader("Piyasa ve haber göstergeleri")
mk = bundle.get("market")
cols = st.columns(5)
meta = [
    ("dxy", "Dolar endeksi", 2), ("tnx", "ABD 10y faiz", 2),
    ("vix", "VIX (korku)", 2), ("oil", "Petrol", 2), ("spx", "S&P 500", 0),
]
for col, (key, label, dg) in zip(cols, meta):
    if mk is not None and not mk.empty and key in mk:
        s = mk[key].dropna()
        d = (s.iloc[-1] / s.iloc[-2] - 1) * 100 if len(s) > 1 else None
        col.metric(label, tl(s.iloc[-1], dg), pct(d) if d is not None else None)

c1, c2 = st.columns(2)
epu, gd = bundle.get("epu"), bundle.get("gdelt")
if epu is not None and len(epu):
    c1.metric("EPU belirsizlik endeksi", tl(epu.iloc[-1], 1))
if gd is not None and len(gd):
    c2.metric("GDELT haber tonu", tl(gd.iloc[-1], 2))
caption("Bu göstergelerin hepsinin geçmiş verisi olduğu için modele girdi olarak "
        "verilebiliyor — katkılarının ölçümü aşağıdaki ablasyon tablosunda.")

# --------------------------------------------------------------------------- #
# Haber duygusu (Claude — katman 3)
# --------------------------------------------------------------------------- #
st.subheader("Günlük haber duygusu")
st.caption("⚠️ Bu skor sayısal tahmini **değiştirmez**, ayrı bir sinyaldir. "
           "Bu göstergenin geçmiş verisi olmadığı için modele girdi olarak verilemiyor; "
           "ileride ölçülebilsin diye bugünden itibaren kaydediliyor.")

headlines = load_headlines(st.session_state.data_nonce)
news_score = None

if not headlines:
    st.info("Haber başlıkları alınamadı.")
elif not ai.has_key():
    st.info(f"{len(headlines)} başlık bulundu. Puanlamak için API anahtarı gerekli.")
else:
    if st.button(f"📰 {len(headlines)} başlığı puanla", key="score_news"):
        st.session_state.news_result = ai.score_news(headlines)
    r = st.session_state.get("news_result")
    if r and not r.get("error"):
        news_score = r.get("skor")
        a, b = st.columns([1, 3])
        a.metric("Duygu skoru", tl(news_score, 2), help="-1 düşüş yönlü · +1 yükseliş yönlü")
        b.write(r.get("ozet", ""))
        if r.get("ana_etkenler"):
            b.caption("Ana etkenler: " + ", ".join(r["ana_etkenler"]))
        u = r.get("usage", {})
        st.caption("Önbellekten geldi — bu istek için ücret ödenmedi." if r.get("cached")
                   else f"{u.get('in', 0)} girdi + {u.get('out', 0)} çıktı token "
                        f"≈ ${u.get('usd', 0):.4f}")
    elif r:
        st.error(r["error"])

with st.expander(f"Başlıklar ({len(headlines)})"):
    for h in headlines:
        st.write("•", h)

# --------------------------------------------------------------------------- #
# Model performansı
# --------------------------------------------------------------------------- #
st.subheader("Model ne kadar güvenilir?")
t1, t4, t2, t3 = st.tabs(["Geçmiş test", "İşlem simülasyonu", "Özellik katkısı (ablasyon)",
                          "Etkili özellikler"])

with t1:
    st.dataframe(res["backtest"], width="stretch")
    caption("Modelin geçmişteki isabeti. **MAPE** ortalama yüzde hata (düşük iyi), "
            "**Yön** fiyatın yönünü doğru bilme oranı. İki çıta satırı var: **naive** "
            "= 'fiyat hiç değişmez', **trend** = 'geçmiş ortalama kadar artar' (yönü hep "
            "yukarı). Bir modelin yön isabeti trend satırından yüksek değilse, yön "
            "konusunda beceri göstermiyor demektir. Test, her gün için sadece o güne "
            "kadarki veriyle eğitilerek yapıldı.")
    g, lo, hi = res.get("gap", 0), res.get("gap_lo", 0), res.get("gap_hi", 0)
    st.caption(f"Naive ile seçilen model arasındaki hata farkı: {g:+.5f} "
               f"(%95 güven aralığı {lo:+.5f} … {hi:+.5f}). "
               + ("Aralık sıfırın üstünde — fark gerçek."
                  if lo > 0 else "**Aralık sıfırı içeriyor — fark gürültü olabilir.**"))

with t4:
    st.markdown("**Bu sinyalle işlem yapsaydım ne olurdu?**")
    cost = st.slider("Tek yön işlem maliyeti (alış–satış makası)", 0.0, 3.0, 0.5, 0.1,
                     format="%%%.1f",
                     help="Banka altın hesabı ~%0,5; kuyumcuda çeyrek altın makası ~%2,3.")
    sim = res.get("sim")
    if sim and res["model"] in sim.get("preds", {}):
        s = model.strategy_sim(sim, res["model"], horizon, cost)
        a, b_, c_ = st.columns(3)
        a.metric("Strateji getirisi", pct(s["strateji_%"], 1))
        b_.metric("Al-tut getirisi", pct(s["al_tut_%"], 1))
        c_.metric("Fark", pct(s["fark_%"], 1),
                  delta=f"{s['fark_%']:+.1f} puan", delta_color="normal")
        st.caption(f"{s['islem']} pencere, {s['degisim']} kez pozisyon değişimi, "
                   f"zamanın {pct(s['altinda_kalma_%'], 0)}'ünde altında kalındı.")
        if s["fark_%"] < 0:
            st.error(
                "**Strateji al-tut'un gerisinde kalıyor.** Yani bu sinyale göre alıp "
                "satmak, hiç dokunmayıp altında beklemekten daha kötü sonuç veriyor. "
                "Maliyeti sıfıra çekip tekrar deneyin: sıfırda bile gerideyse sorun "
                "maliyet değil, sinyalin kendisidir.",
                icon="🚫",
            )
        else:
            st.success("Strateji bu maliyet seviyesinde al-tut'u geçiyor.", icon="✅")
    else:
        st.info("Seçilen model sinyal üretmiyor (naive), simülasyon yapılamıyor.")
    caption("Kural: model yükseliş derse altın tut, demezse TL'de bekle. Çakışmayan "
            "pencerelerle, pozisyon her değiştiğinde iki yönlü makas ödenerek hesaplandı. "
            "Düşük tahmin hatası kâr demek değildir — işlem yönle yapılır ve makas ödenir, "
            "bu yüzden karar öncesi bakılacak asıl tablo budur.")

with t2:
    st.dataframe(res["ablation"], width="stretch", hide_index=True)
    caption("Özellikler kademeli eklenerek aynı test tekrarlandı. Eklemek her zaman "
            "iyileştirmez: elde ~2.200 gün veri varken çok fazla özellik aşırı öğrenmeye "
            "yol açabilir. Panel, bu tabloda en iyi çıkan seti kullanıyor. "
            "Not: hem özellik seti hem model aynı test üzerinden seçildiği için "
            "gerçek hata buradakinden bir miktar yüksek olabilir.")

with t3:
    if res.get("importance"):
        st.plotly_chart(importance_chart(res["importance"]), width="stretch",
                        config={"displayModeBar": False})
        caption("Bir özellik karıştırıldığında modelin hatası ne kadar artıyor — "
                "çubuk ne kadar uzunsa özellik o kadar belirleyici.")
    else:
        st.info("Seçilen model özellik kullanmıyor (naive/drift), bu yüzden katkı grafiği yok.")

# --------------------------------------------------------------------------- #
# AI yorumu
# --------------------------------------------------------------------------- #
st.subheader("Yapay zekâ yorumu")
if not ai.has_key():
    st.info("Yorum için `.env` dosyasına `ANTHROPIC_API_KEY` ekleyin.")
else:
    if st.button("🤖 AI Yorum Al", key="get_comment"):
        mkl = mk.iloc[-1] if mk is not None and not mk.empty else {}
        ctx = {
            **{k: res[k] for k in
               ("last_price", "price", "lo", "hi", "ret", "model",
                "best_set", "best_mape", "naive_mape", "beats_naive")},
            "horizon": horizon,
            "yon_isabeti": float(res["backtest"].loc[res["model"], "Yon_%"])
            if res["model"] in res["backtest"].index else None,
            "volatilite_20gun": float(df["vol_20"].iloc[-1] * 100),
            "rsi": float((df["rsi_14"].iloc[-1] + 0.5) * 100),
            "usdtry_5gun_degisim": float(df["usdtry_5"].iloc[-1] * 100),
            "dxy_5gun_degisim": float(df["dxy_5"].iloc[-1] * 100) if "dxy_5" in df else None,
            "abd_10y_faiz": float(mkl["tnx"]) if "tnx" in mkl else None,
            "vix": float(mkl["vix"]) if "vix" in mkl else None,
            "haber_skoru": news_score,
        }
        st.session_state.comment = ai.comment(ctx)

    cm = st.session_state.get("comment")
    if cm and not cm.get("error"):
        st.info(cm["text"])
        u = cm.get("usage", {})
        st.caption("Önbellekten geldi — bu istek için ücret ödenmedi." if cm.get("cached")
                   else f"{u.get('in', 0)} girdi + {u.get('out', 0)} çıktı token "
                        f"≈ ${u.get('usd', 0):.4f}")
    elif cm:
        st.error(cm["error"])

caption("Yorum yalnızca düğmeye basınca üretilir ve aynı sayılar için önbellekten "
        "gelir — bu sayede token harcaması günde birkaç çağrıyla sınırlı kalır.")

# --------------------------------------------------------------------------- #
st.divider()
st.caption(
    f"**Bu bir yatırım tavsiyesi değildir.** Fiyat tahmini doğası gereği belirsizdir. · "
    f"Veri: Yahoo Finance, truncgil, policyuncertainty.com, GDELT, Google News · "
    f"Son fiyat güncellemesi: {live.get('updated', '—')} · "
    f"Kalibrasyon çarpanı: {tl(bundle.get('scale', 1), 4)}"
)
