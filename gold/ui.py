"""Arayüz yardımcıları: Türkçe sayı biçimi, tema renkleri, grafik.

Biçimlendirme mantığı tek yerde toplandı ki panel baştan sona tutarlı görünsün.
Renkler doğrulanmış paletten alındı (bkz. dataviz palette): seri rengi mavi,
hem açık hem koyu zeminde 3:1 kontrastı geçiyor. Altın sarısı bilinçli olarak
veri çizgisinde kullanılmadı — açık zeminde kontrastı 2.17:1'de kalıyor.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# Doğrulanmış palet — light / dark
LIGHT = {
    "series": "#2a78d6",
    "band": "rgba(42,120,214,0.15)",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "muted": "#898781",
    "text": "#0b0b0b",
    "surface": "rgba(0,0,0,0)",
}
DARK = {
    "series": "#3987e5",
    "band": "rgba(57,135,229,0.18)",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "muted": "#898781",
    "text": "#ffffff",
    "surface": "rgba(0,0,0,0)",
}


def theme() -> dict:
    """Streamlit'in aktif teması. Tespit edilemezse açık tema."""
    try:
        base = st.get_option("theme.base")
    except Exception:
        base = None
    return DARK if base == "dark" else LIGHT


# --------------------------------------------------------------------------- #
def tl(x, digits: int = 2) -> str:
    """6199.69 → '6.199,69' (Türkçe binlik/ondalık ayracı)."""
    if x is None or pd.isna(x):
        return "—"
    s = f"{float(x):,.{digits}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pct(x, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"%{tl(x, digits)}"


def caption(text: str) -> None:
    """Panel altı sade açıklama — jargonu okunur hale getirmek için."""
    st.caption(text)


# --------------------------------------------------------------------------- #
def price_chart(hist: pd.Series, pred: dict, horizon: int):
    """Geçmiş fiyat + tahmin + belirsizlik bandı.

    Bant, son gerçek fiyattan başlayıp ufka doğru açılıyor: belirsizlik zamanla
    büyüdüğü için dürüst gösterim bu.
    """
    import plotly.graph_objects as go

    c = theme()
    last_date = hist.index[-1]
    future = last_date + pd.Timedelta(days=horizon)
    p0 = float(hist.iloc[-1])

    fig = go.Figure()

    # Belirsizlik bandı (önce çizilir ki çizginin altında kalsın)
    fig.add_trace(go.Scatter(
        x=[last_date, future], y=[p0, pred["hi"]],
        mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[last_date, future], y=[p0, pred["lo"]],
        mode="lines", line=dict(width=0), fill="tonexty", fillcolor=c["band"],
        hoverinfo="skip", name="belirsizlik aralığı",
    ))

    # Geçmiş
    fig.add_trace(go.Scatter(
        x=hist.index, y=hist.values, mode="lines", name="gerçekleşen",
        line=dict(color=c["series"], width=2),
        hovertemplate="%{x|%d.%m.%Y}<br>%{y:,.0f} TL<extra></extra>",
    ))

    # Tahmin — aynı seri, kesikli çizgiyle ayrılıyor
    fig.add_trace(go.Scatter(
        x=[last_date, future], y=[p0, pred["price"]], mode="lines+markers",
        name=f"{horizon} günlük tahmin",
        line=dict(color=c["series"], width=2, dash="dot"),
        marker=dict(size=9, color=c["series"]),
        hovertemplate="%{x|%d.%m.%Y}<br>%{y:,.0f} TL<extra></extra>",
    ))

    # Doğrudan etiket — her noktaya sayı basmak yerine sadece tahmine
    fig.add_annotation(
        x=future, y=pred["price"], text=f"<b>{tl(pred['price'], 0)} TL</b>",
        showarrow=False, xanchor="left", xshift=10,
        font=dict(color=c["text"], size=13),
    )

    fig.update_layout(
        height=420,
        margin=dict(l=0, r=90, t=10, b=0),
        paper_bgcolor=c["surface"], plot_bgcolor=c["surface"],
        hovermode="x unified",
        font=dict(color=c["muted"], size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=c["muted"])),
        xaxis=dict(showgrid=False, linecolor=c["axis"], tickformat="%b %Y"),
        yaxis=dict(gridcolor=c["grid"], zeroline=False, linecolor=c["axis"],
                   ticksuffix=" TL", tickformat=",.0f"),
    )
    return fig


def importance_chart(items: list[tuple[str, float]]):
    """En etkili özellikler — yatay bar, tek renk (kategori değil, sıralama)."""
    import plotly.graph_objects as go

    c = theme()
    items = list(reversed(items))
    fig = go.Figure(go.Bar(
        x=[v for _, v in items], y=[k for k, _ in items],
        orientation="h", marker=dict(color=c["series"]),
        hovertemplate="%{y}: %{x:.5f}<extra></extra>",
    ))
    fig.update_layout(
        height=max(180, 34 * len(items)),
        margin=dict(l=0, r=0, t=6, b=0),
        paper_bgcolor=c["surface"], plot_bgcolor=c["surface"],
        font=dict(color=c["muted"], size=12),
        xaxis=dict(showgrid=True, gridcolor=c["grid"], zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False),
    )
    return fig
