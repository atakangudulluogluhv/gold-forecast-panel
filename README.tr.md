# 🥇 Altın/TL Tahmin Paneli

Gram altının TL fiyatını geçmiş verilerle tahmin eden, tahminin ne kadar güvenilir
olduğunu geçmişe dönük testle ölçen ve sonucu Claude ile yorumlayan Streamlit paneli.

Panelin ayırt edici yanı tahmin üretmesi değil, **tahminin sınırını ölçüp ekranda
göstermesi**. Yön tahmini beceri göstermiyorsa kırmızı uyarı basar; sinyale göre işlem
yapmak al-tut'un gerisinde kalıyorsa bunu sayıyla söyler. Ayrıntı: *Ölçülen bulgu* bölümü.

> **Bu bir yatırım tavsiyesi aracı değildir.** Alım-satım önerisi üretmez; neden
> üretmediği de ölçülmüş bir sonuçtur, tercih değil.

## Çalıştırma

**Windows — tek adım:** `baslat.bat` dosyasına çift tıklayın.

Betik gerekli her şeyi kendi yapar: sanal ortam oluşturur, paketleri kurar, `.env`
dosyasını hazırlar ve paneli açar. İlk çalıştırmada paket kurulumu birkaç dakika sürer,
sonraki açılışlar saniyeler içindedir.

> 💡 Masaüstünden açmak için: `baslat.bat` → sağ tık → **Kısayol oluştur** → kısayolu
> masaüstüne taşıyın.

**Elle çalıştırmak isterseniz:**

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
streamlit run app.py
```

Panel kapatmak için terminalde `Ctrl+C`.

## API anahtarı

Yapay zekâ yorumu ve haber puanlaması için gerekli. **Anahtar olmadan da panel tam
çalışır** — yalnızca bu iki özellik devre dışı kalır.

1. https://console.anthropic.com → **Settings → API keys → Create Key**
2. Anahtar yalnızca oluşturulduğu anda bir kez gösterilir; **kopyala düğmesiyle** alın
   (listeden kopyalarsanız maskeli hali gelir ve geçersiz olur)
3. **Billing** kısmından kredi yükleyin — API ön ödemelidir
4. `.env` dosyasını açıp yapıştırın:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Tırnak yok, boşluk yok. Kaydedip paneli yeniden başlatın; kenar çubuğunda
"Claude API anahtarı: ✅ tanımlı" yazmalı.

⚠️ Proje klasörü OneDrive/Dropbox içindeyse `.env` buluta senkronize olur. Anahtarınızın
buluta çıkmasını istemiyorsanız projeyi senkronize edilmeyen bir klasöre taşıyın.

## İlk açılış

Veri indirilir ve model eğitilir; ufuk başına ~45 saniye sürer. Sonuçlar `cache/`
klasörüne yazıldığı için sonraki açılışlar anlıktır. Yeniden hesaplamak için kenar
çubuğundaki **Verileri yenile** / **Modeli yeniden eğit** düğmelerini kullanın.

## Mimari — kim ne yapıyor?

**Tahmini dil modeli yapmaz.** Fiyat tahmini bilgisayarınızda çalışan bir regresyon
modelinden (scikit-learn) gelir ve hiç token harcamaz. Claude yalnızca iki dar işte
kullanılır: günlük haber başlıklarını puanlamak ve hazır sayı özetinden kısa bir yorum
yazmak.

Bunun nedeni ölçülebilirlik: bir dil modeline ham fiyat serisi verip "tahmin et" demek
her sorguda değişen, geçmişe dönük test edilemeyen bir sayı üretir. Regresyonun ise
ölçülebilir bir başarısı vardır — paneldeki tüm doğruluk rakamları o ölçümden gelir.

```
Yahoo Finance ─┐
truncgil ──────┼─→ gram altın TL serisi ─→ özellikler ─→ regresyon ─→ tahmin
EPU / GDELT ───┘                                              │
                                                              ↓
                                                     Claude → kısa yorum
```

### Veri kaynakları (hepsi ücretsiz, API anahtarı gerektirmez)

| Kaynak | Ne verir |
|---|---|
| Yahoo Finance | Altın (`GC=F`), dolar/TL (`TRY=X`), dolar endeksi, ABD 10y faiz, VIX, petrol, S&P 500 |
| truncgil | Canlı gram altın / ons / dolar fiyatı |
| policyuncertainty.com | Gazete tabanlı günlük belirsizlik endeksi (EPU), 1985'ten beri |
| GDELT | Dünya haberlerinin altın konulu günlük duygu tonu, 2018'den beri |
| Google News + Investing RSS | Güncel başlıklar (Claude puanlaması için) |

### Haber verisinin üç katmanı

Ayrım "haber mi değil mi" değil, **"geçmişi var mı yok mu"** üzerinden yapılır — çünkü
geçmişi olmayan bir veriyle modelin iyileştiğini iddia edemezsiniz.

| Katman | Modele girer mi? | Neden |
|---|---|---|
| Piyasa göstergeleri (dolar endeksi, faiz, VIX…) | Evet | 10 yıllık günlük geçmiş var → test edilebilir |
| Haber endeksleri (EPU, GDELT) | Evet | Günlük geçmiş var → test edilebilir |
| Bugünün başlıkları (Claude puanı) | Hayır | Geçmişi yok → ölçülemez |

Üçüncü katman panelde ayrı bir sinyal olarak gösterilir ve `cache/sentiment_history.csv`
dosyasına biriktirilir; birkaç ay sonra ölçülebilir hale gelir.

## Ölçülen bulgu: sömürülebilir bir edge yok

Panelin en önemli çıktısı tahmin değil, tahminin sınırını göstermesi. Üç bağımsız ölçüm
aynı sonuca çıkıyor:

**1. Yön isabeti trend artefaktı.** Altın/TL geçmişte 30 günlük pencerelerin %72'sinde
yükselmiş. Modelin %71,8'lik yön isabeti bunun altında — yani "hep yükselir" diyen sabit
bir tahminden iyi değil. 7 günde fark +0,6 puan, yine gürültü.

| Ufuk | Model yön | "Hep yükselir" | Gerçek üstünlük |
|---|---|---|---|
| 7 gün | %63,4 | %62,9 | +0,6 puan |
| 30 gün | %71,8 | %72,4 | −0,6 puan |

**2. Sinyalle işlem yapmak al-tut'un gerisinde.** "Model yükseliş derse altın tut, demezse
TL'de bekle" stratejisi, **sıfır işlem maliyetinde bile** kaybediyor:

| Maliyet | Strateji | Al-tut | Fark |
|---|---|---|---|
| %0 | %327 | %350 | −23 puan |
| %0,5 (banka) | %250 | %350 | −100 puan |
| %2 (kuyumcu makası) | %19 | %350 | −331 puan |

**3. Olasılıklar taban orandan bilgili değil.** 2–3 günlük yükseliş olasılığının Brier
beceri skoru sıfırın altında — model geçmişteki yükseliş oranını tekrar etmekten fazlasını
yapmıyor.

MAPE farkı istatistiksel olarak anlamlı çıkıyor (naive 2,62% → model 2,52%), ama bu
*büyüklük* tahmininde küçük bir iyileşme; işlem *yönle* yapılır ve yönde beceri yok.

Panel bu üç ölçümü de ekranda gösterir ve olumsuz çıktığında kırmızı uyarı basar.
**Bu yüzden bir karar/yatırım aracı değildir** — eksik bir özellik değil, ölçülmüş bir
sonuçtur.

## Dürüstlük notları

- Her tahmin, **"fiyat hiç değişmez"** (naive) varsayımıyla karşılaştırılır. Model bunu
  geçemiyorsa panel bunu açıkça yazar ve tahmin olarak bugünkü fiyatı gösterir.
  Gerçekte kısa vadede (1 gün) genellikle geçemez — altın günlük ölçekte rastgele
  yürüyüşe çok yakındır.
- **Ablasyon tablosu** özellik eklemenin işe yarayıp yaramadığını gösterir. Bu projede
  piyasa ve haber özellikleri bazı vadelerde sonucu *kötüleştiriyor* — elde ~2.200 gün
  veri varken 45 özellik aşırı öğrenmeye yol açıyor. Panel bu durumda daha dar özellik
  setini kullanır.
- Backtest, her gün için yalnızca o güne kadarki veriyle eğitilerek yapılır ve hedef
  ufku kadar boşluk (embargo) bırakılır — yoksa model cevabı görmüş olur.
- Hem özellik seti hem model aynı test üzerinden seçildiği için raporlanan hata bir
  miktar iyimser olabilir.

## Token maliyeti

Claude çağrıları `claude-haiku-4-5` ile yapılır ve diske önbelleklenir.

Gerçek çağrılarla ölçülmüş değerler:

| İş | Sıklık | Token (girdi + çıktı) | Maliyet |
|---|---|---|---|
| Haber puanlaması | Günde en fazla 1 | 1.091 + 125 | ~0,08 TL |
| Yorum | Düğmeye basınca, aynı sayılar için önbellekten | 451 + 412 | ~0,12 TL |

Kullanıma göre **ayda ~6–13 TL**. Ham fiyat serisi hiçbir zaman gönderilmez — yorum için
giden tek satır şuna benzer:

```
gram_altin_fiyati=6180.41 TL | vade=7 gun | tahmin=6229.01 TL |
tahmin_araligi=6009.34-6483.31 TL | model_ortalama_hatasi=%2.52 |
naive_ortalama_hatasi=%2.62 | naiveyi_geciyor=evet | rsi=55.21 | vix=17.27 | ...
```

Aynı seriyi ham göndermek ~50.000 token olurdu. Kullanılan token ve maliyet her çağrıdan
sonra arayüzde gösterilir; önbellekten gelen yanıtlarda "ücret ödenmedi" yazar.

> Kısaltmalardan kaçınıldı: ilk sürümde `ufuk=7g` yazıyordu ve model bunu bir kez
> "7 gram" diye okudu. Birkaç token tasarrufu, yanlış çıktıya değmiyor.

## Dosya düzeni

```
baslat.bat          Tek tıkla başlatıcı (venv + kurulum + çalıştırma)
app.py              Streamlit arayüzü
gold/config.py      semboller, ufuklar, dosya yolları
gold/data.py        veri çekimi, kalibrasyon, önbellek
gold/features.py    özellik üretimi (3 grup: fiyat / piyasa / haber)
gold/model.py       backtest, ablasyon, trend çıtası, işlem simülasyonu, tahmin
gold/proba.py       2-3 günlük yükseliş olasılığı + kalibrasyon karnesi
gold/news.py        RSS başlıkları
gold/ai.py          Claude çağrıları (token disiplini burada)
gold/ui.py          Türkçe sayı biçimi, tema renkleri, grafikler
```

---

**Bu bir yatırım tavsiyesi değildir.** Fiyat tahmini doğası gereği belirsizdir ve
buradaki sonuçlar eğitim/araştırma amaçlıdır.
