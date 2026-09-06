"""Claude katmanı — iki dar iş, ikisi de cache'li.

Token disiplini bu dosyanın tek tasarım önceliği:
  1. Ham fiyat serisi asla gönderilmiyor; sadece yuvarlanmış özet sayılar
  2. `max_tokens` her iki çağrıda da dar tutuluyor
  3. Otomatik çağrı yok — Streamlit her etkileşimde script'i baştan çalıştırdığı
     için otomatik çağrı token'ı sessizce katlar
  4. Sonuçlar diske yazılıyor; aynı girdi ikinci kez para harcamıyor
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date

from . import config as C

NEWS_SYSTEM = (
    "Sen bir finans haber analistisin. Sana altın/döviz ile ilgili haber başlıkları "
    "verilecek. Bunların altın fiyatı üzerindeki genel etkisini değerlendir. "
    "Sadece verilen başlıklara dayan, dışarıdan bilgi ekleme, sayı uydurma. "
    "skor: -1 (güçlü düşüş yönlü) ile +1 (güçlü yükseliş yönlü) arası. "
    "ozet: tek cümle, en fazla 20 kelime. Yatırım tavsiyesi verme."
)

NEWS_SCHEMA = {
    "type": "object",
    "properties": {
        "skor": {"type": "number"},
        "ana_etkenler": {"type": "array", "items": {"type": "string"}},
        "ozet": {"type": "string"},
    },
    "required": ["skor", "ana_etkenler", "ozet"],
    "additionalProperties": False,
}

COMMENT_SYSTEM = (
    "Sen bir finans analistisin. Sana bir altın tahmin modelinin özet sayıları verilecek. "
    "3-4 cümlelik, düz paragraf halinde Türkçe bir yorum yaz.\n"
    "Kurallar:\n"
    "- Sadece verilen sayıları kullan, yeni sayı uydurma.\n"
    "- Modelin 'naive' (fiyat değişmez) varsayımını geçip geçmediğini mutlaka belirt.\n"
    "- Tahmin aralığının genişliğine değin — asıl bilgi tek bir sayı değil, aralıktır.\n"
    "- Belirsizliği saklama. Yatırım tavsiyesi verme, alım/satım önerme.\n"
    "- Başlık, markdown biçimlendirmesi, madde işareti veya liste KULLANMA. "
    "Sadece düz metin paragraf yaz."
)


def has_key() -> bool:
    """Gerçek bir anahtar var mı.

    `.env.example`'daki `sk-ant-...` yer tutucusu kopyalandığında düğmeler açık
    görünüp çağrıda hata veriyordu; yer tutucuyu 'anahtar yok' sayıyoruz.
    """
    k = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    return len(k) > 30 and not k.endswith("...")


def _client():
    import anthropic

    return anthropic.Anthropic()


def _load(path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _cost(usage) -> dict:
    """Token sayısı ve USD maliyeti — arayüzde şeffaf gösterilsin diye."""
    tin, tout = usage.input_tokens, usage.output_tokens
    return {
        "in": tin,
        "out": tout,
        "usd": tin / 1e6 * C.PRICE_IN_PER_MTOK + tout / 1e6 * C.PRICE_OUT_PER_MTOK,
    }


# --------------------------------------------------------------------------- #
def score_news(headlines: list[str], force: bool = False) -> dict:
    """Başlıkları tek skora indirger. Günde en fazla bir çağrı."""
    if not headlines:
        return {"error": "Haber alınamadı."}
    if not has_key():
        return {"error": "API anahtarı yok."}

    today = str(date.today())
    store = _load(C.F_NEWS)
    if not force and today in store:
        return {**store[today], "cached": True}

    try:
        resp = _client().messages.create(
            model=C.CLAUDE_MODEL,
            max_tokens=250,
            system=NEWS_SYSTEM,
            messages=[{"role": "user", "content": "\n".join(headlines)}],
            output_config={"format": {"type": "json_schema", "schema": NEWS_SCHEMA}},
        )
    except Exception as e:
        return {"error": f"Claude çağrısı başarısız: {type(e).__name__}"}

    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"error": "Yanıt çözümlenemedi."}

    out = {**parsed, "usage": _cost(resp.usage), "n": len(headlines), "cached": False}
    store[today] = out
    _save(C.F_NEWS, store)
    _append_history(today, parsed.get("skor"), len(headlines))
    return out


def _append_history(day: str, score, n: int) -> None:
    """Skoru CSV'ye biriktirir.

    Bugünün Türkçe başlıkları modele özellik olarak giremiyor çünkü geçmişi yok.
    Buradan itibaren biriktiriyoruz ki 6-12 ay sonra ölçülebilir hale gelsin.
    """
    if score is None:
        return
    new = not C.F_SENT_HIST.exists()
    with C.F_SENT_HIST.open("a", encoding="utf-8") as fh:
        if new:
            fh.write("tarih,skor,baslik_sayisi\n")
        fh.write(f"{day},{score},{n}\n")


# --------------------------------------------------------------------------- #
def build_payload(ctx: dict) -> str:
    """Model çıktısını ~15 sayıya indirger.

    Ham seri yerine bu gidiyor — çağrı başına ~500 token yerine ~50.000 token farkı.
    """
    def n(x, d=2):
        return "-" if x is None else round(float(x), d)

    # Birim kısaltmaları açık yazılıyor: "ufuk=7g" ifadesini model bir kez
    # "7 gram" diye okudu, kısaltma tasarrufu yanlış çıktıya değmiyor.
    parts = [
        f"gram_altin_fiyati={n(ctx['last_price'])} TL",
        f"vade={ctx['horizon']} gun",
        f"tahmin={n(ctx['price'])} TL",
        f"tahmin_araligi={n(ctx['lo'])}-{n(ctx['hi'])} TL",
        f"beklenen_degisim=%{n(ctx['ret'] * 100)}",
        f"model={ctx['model']}",
        f"ozellik={ctx['best_set']}",
        f"model_ortalama_hatasi=%{n(ctx['best_mape'], 2)}",
        f"naive_ortalama_hatasi=%{n(ctx['naive_mape'], 2)}",
        f"naiveyi_geciyor={'evet' if ctx['beats_naive'] else 'hayir'}",
    ]
    for k in ("yon_isabeti", "volatilite_20gun", "rsi", "usdtry_5gun_degisim",
              "dxy_5gun_degisim", "abd_10y_faiz", "vix", "haber_skoru"):
        if ctx.get(k) is not None:
            parts.append(f"{k}={n(ctx[k])}")
    return " | ".join(parts)


def comment(ctx: dict, force: bool = False) -> dict:
    """Özet sayılardan kısa yorum. Sadece düğmeye basınca çağrılır."""
    if not has_key():
        return {"error": "API anahtarı yok."}

    payload = build_payload(ctx)
    key = hashlib.sha256(payload.encode()).hexdigest()[:16]
    store = _load(C.F_COMMENTS)
    if not force and key in store:
        return {**store[key], "cached": True}

    try:
        resp = _client().messages.create(
            model=C.CLAUDE_MODEL,
            # 300'de 4 cümlelik yorum ortasından kesiliyordu; yarım cümle
            # göstermektense birkaç token fazla harcamak daha iyi.
            max_tokens=450,
            system=COMMENT_SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
    except Exception as e:
        return {"error": f"Claude çağrısı başarısız: {type(e).__name__}"}

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    out = {"text": text, "usage": _cost(resp.usage), "cached": False,
           "truncated": resp.stop_reason == "max_tokens"}
    store[key] = out
    _save(C.F_COMMENTS, store)
    return out
