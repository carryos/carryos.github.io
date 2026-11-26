# CarryOS — web sitesi

Bilgisayarın, cebinde. CarryOS'un tanıtım sitesi: saf HTML + CSS + JS, derleme adımı yok, bağımlılık yok.
Türkçe (varsayılan) ve İngilizce içerir; sağ üstteki **TR | EN** düğmesiyle değişir.

## 1) Önce doldurman gereken yerler

Tüm bağlantılar tek dosyada: **`assets/js/config.js`**

```js
window.CARRYOS = {
  repoUrl:     "https://www.example.com",   // GitHub deposunun adresi
  downloadUrl: "https://www.example.com",   // İmaj dosyasının indirme bağlantısı
  releasesUrl: "https://www.example.com",   // Sürüm notları sayfası
  version:     "v0.1",
  imageSize:   "≈ 14 GiB",
  sha256:      "—"                          // SHA-256 toplamını buraya yapıştır
};
```

Ek olarak `index.html` içinde, paylaşım önizlemesi için iki adresi kendi site adresinle değiştir:
`og:image` ve `og:url` (şu an `https://www.example.com/...`).

## 2) GitHub Pages ile yayınlama

1. GitHub'da yeni bir depo oluştur (ör. `carryos`). 
2. Bu klasörün **içindekileri** (klasörün kendisini değil) depoya yükle:
   - Tarayıcıdan: depo sayfasında **Add file → Upload files** ve dosyaları sürükle, ya da
   - Komut satırından:
     ```bash
     git init -b main
     git add .
     git commit -m "CarryOS sitesi"
     git remote add origin https://github.com/KULLANICI/DEPO.git
     git push -u origin main
     ```
3. Depoda **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   dal: **main**, klasör: **/ (root)** → **Save**.
4. Birkaç dakika sonra site `https://KULLANICI.github.io/DEPO/` adresinde yayında olur.

> `404.html` kök adres varsayar (`/assets/...`). Siteyi **özel alan adıyla** ya da deponu
> `KULLANICI.github.io` adıyla yayınlarsan 404 sayfası da tam görünür. `KULLANICI.github.io/DEPO/` altında
> ana site sorunsuz çalışır; yalnızca 404 sayfasının stili yüklenmeyebilir.

**Özel alan adı:** Settings → Pages → Custom domain. Alan adının DNS ayarlarını GitHub'ın
yönergesine göre yap.

## 3) Yerelde önizleme

```bash
python3 -m http.server 8000
# tarayıcıda http://localhost:8000
```

## 4) Yapı

```
index.html            sayfanın tamamı
404.html              bulunamadı sayfası
site.webmanifest      uygulama bilgisi / simgeler
assets/css/style.css  tüm tasarım (renkler :root içinde)
assets/js/config.js   bağlantılar ve sürüm bilgisi  ← düzenle
assets/js/i18n.js     İngilizce çeviriler ve dinamik metinler
assets/js/main.js     animasyonlar, dil, etkileşimler
assets/img/           logo, yazı logosu, simgeler, kum tepeleri
assets/fonts/         Inter + Lora (yerel, harici istek yok)
```

- **Metin değiştirmek:** Türkçe metinler `index.html` içinde, İngilizce karşılıkları `assets/js/i18n.js` içinde
  aynı `data-i18n` anahtarıyla durur.
- **Renkleri değiştirmek:** `assets/css/style.css` başındaki `:root` bloğu.
- **Harici istek yok:** yazı tipleri, görseller ve betikler site içinden gelir; izleme/analitik yoktur.

## 5) Lisans notları

Logolar ve yazı logosu proje sahibine aittir. Yazı tipleri SIL OFL 1.1 lisanslıdır (bkz. `assets/fonts/`).
