"""Proje geneli sabitler. Tek yerden ayarlanır."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)

# --- Veri kaynakları ---------------------------------------------------------
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

GOLD_SYM = "GC=F"      # altın vadeli, USD/ons
USDTRY_SYM = "TRY=X"   # USD/TRY

# Piyasa göstergeleri (katman 1) — sembol: okunabilir ad
MARKET_SYMS = {
    "DX-Y.NYB": "dxy",    # dolar endeksi
    "^TNX": "tnx",        # ABD 10 yıllık tahvil faizi
    "^VIX": "vix",        # korku endeksi
    "CL=F": "oil",        # petrol
    "^GSPC": "spx",       # S&P 500
}

TRUNCGIL_URL = "https://finans.truncgil.com/today.json"

EPU_URL = "https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv"

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "gold price"

# Türkçe sorgu tırnaklı: yalın "altın fiyat" araması Vietnam/SJC haberlerini de
# çekiyordu, tam ifade eşleşmesi bunu eliyor.
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%22gram+alt%C4%B1n%22+OR+%22%C3%A7eyrek+alt%C4%B1n%22"
    "+OR+%22alt%C4%B1n+fiyat%C4%B1%22&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=gold+price+fed+OR+%22dollar+index%22"
    "&hl=en-US&gl=US&ceid=US:en",
    "https://tr.investing.com/rss/news_301.rss",
]

# --- Model -------------------------------------------------------------------
HORIZONS = [1, 7, 30]
PROBA_HORIZONS = (2, 3)   # "2-3 gün içinde yükselir mi" paneli
TROY_OUNCE_G = 31.1034768
MIN_TRAIN = 500      # backtest'te ilk eğitim penceresi (gün)
REFIT_EVERY = 20     # kaç günde bir yeniden fit
HISTORY_RANGE = "10y"

# --- Claude ------------------------------------------------------------------
CLAUDE_MODEL = "claude-haiku-4-5"
PRICE_IN_PER_MTOK = 1.0    # USD
PRICE_OUT_PER_MTOK = 5.0   # USD

# --- Cache dosyaları ---------------------------------------------------------
F_PRICES = CACHE / "prices.csv"
F_MARKET = CACHE / "market.csv"
F_EPU = CACHE / "epu.csv"
F_GDELT = CACHE / "gdelt.csv"
F_MODELS = CACHE / "models.pkl"
F_COMMENTS = CACHE / "ai_comments.json"
F_NEWS = CACHE / "news_sentiment.json"
F_SENT_HIST = CACHE / "sentiment_history.csv"

CACHE_TTL_SEC = 3600  # 1 saatten yeni cache için ağa çıkma
