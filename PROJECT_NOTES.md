# Proje Devir Notu — Ticaret Bilgi Masası / mevzuat-mcp

Son güncelleme: 2 Eylül 2026

## Proje nedir
FastMCP tabanlı Türkiye mevzuat + Ticaret Bakanlığı bilgi sunucusu ve üstündeki web uygulaması
("Ticaret Bilgi Masası", "Gümrükçe'ye Sor"). ASGI giriş noktası `app.py`, arayüz `web/`.
Yerelde çalıştırma: `scripts/dev.sh` (anahtar gerekmez; veri `.dev-data/` altına yazılır).

## 2 Eylül 2026 oturumu — ne yapıldı

### Doğrulananlar (yerel sunucu, Playwright ile bir kullanıcı gibi gezildi)
- 103 birim testi geçiyor (`pytest`).
- Açılış sayfası, /app (Kaynak araştır, Genel mevzuat, Gümrükçe'ye Sor ve 6 alt sekmesi),
  Hesabım diyaloğu (Özet, Kanıt dosyaları, Paketler), /admin, /gizlilik, /kullanim-kosullari
  masaüstü (1440) ve mobil (390) genişlikte konsol hatasız açılıyor.
- Uçtan uca akışlar çalışıyor: katalog araması + belge okuyucu, genel mevzuat araması,
  ön değerlendirme (anahtarsız "yalnız kanıt paketi" modunda), Tarife & Maliyet sorgusu
  (610342000000 · Çin → %12 GV, %39 İGV kaynak satırlarıyla), Kontroller sorgusu
  (2026/18 tebliğ eşleşmesi), kanıt dosyası kaydı ve Hesabım'da listelenmesi, admin özeti.
- Google girişi yapılandırılmadığında "/auth/google" düzgün biçimde açılış sayfasına
  bilgilendirme ile döndürüyor.

### Düzeltilen hatalar
- Mobilde (≤840px) üst çubuk 4px taşıyor, sayfa yatay kaydırılabiliyordu → `web/app.css`
  840px media bloğu (`.topbar`, `.topbar-tools`, `.app-login/.app-account`).
- Kenar çubuğu "Canlı kapsam" kartında değerler etiketle bitişik ve hizasız
  ("Yenileme1 sa. / tam 6 sa.") → `.coverage dl div`, `.coverage dd`.

### Görsel yumuşatma (istek: "daha yumuşak olsun")
- `web/app.css` sonuna "Yumuşak yüzey katmanı" eklendi: `--radius-*` ve `--shadow-card`
  belirteçleri, kartlar/alanlar/düğmeler/sekmeler/diyaloglar için köşe yuvarlatma, daha açık
  çizgi rengi, odakta yumuşak halka. Izgara, tipografi ve metinler değişmedi; koyu tema
  doğrulandı.
- `web/landing.css` sonuna aynı katman: sert ofset gölgeler yerine yumuşak gölge, kartlar
  ve düğmelerde köşe yuvarlatma.
- Geri almak için iki dosyanın sonundaki katman blokları silinir.
- Dikkat: köşe yuvarlatma için `overflow: hidden` yalnızca kaydırmayan kutulara verildi.
  `.customs-view-tabs` mobilde yatay kaydırır (`overflow-x: auto` korunmalı), `.account-dialog`
  ve `.consultation-dialog` dikey kaydırır (overflow verilmemeli). Bu iki regresyon aynı
  oturumda yakalanıp geri alındı; yeni kutu yuvarlatırken aynı kontrolü yapın.

### Yerelde doğrulanamayanlar (anahtar/dış servis gerekir)
- Gerçek Google OAuth ile hesap açma (oturum, `AUTH_SESSION_SECRET` ile imzalanmış test
  çerezi üretilerek taklit edildi; gerçek kayıt akışı denenmedi).
- Stripe checkout / portal / webhook (`billing_mode: disabled`).
- OpenRouter görsel analiz ve GTİP aday üretimi (anahtarsız akış "evidence_only" döndü).
- Canlı Bedesten/ticaret.gov.tr eşitlemesinde 40 sayfa güvenlik sınırı hataları
  (`gumruk`, `destekler` kaynakları) — tasarım gereği; katalog yine 6 binin üstünde kayıtla dolu.

## Bekleyen işler / plan (öncelik sırasıyla)

### P1 — Kullanıcının hemen fark edeceği
1. **Katalog eşitleme sınırı**: `gumruk` ve `destekler` kaynaklarında 40 sayfa sınırı
   dolduğu için 36 + 79 sayfa taranmıyor. Sınırı kaynak bazında artırmak veya kalan
   sayfaları bir sonraki saatlik turda devam ettirmek (kaldığı yerden) gerekir.
2. **Ön değerlendirme sonuç ekranı çok uzun**: kanıt defteri 30+ kaynak kartını art arda
   listeliyor. Kaynak defteri katlanabilir (`details`) olmalı, önce özet/riskler görünmeli.
3. **Mobil menü**: 390px'te "Gümrükçe'ye Sor" sekmesi iki satıra bölünüyor ve alt
   sekmeler (6 adet) yatay kaydırma gerektiriyor; mobilde ikon+kısa etiket veya açılır
   menü düşünülmeli.
4. **Boş durumlar**: "Yayındaki danışmanlar" ve "Değişiklikler" panelleri ilk kullanımda
   yalnızca "yok" diyor; ne yapılacağını gösteren kısa bir yönlendirme kartı eklenmeli.

### P2 — Eksik/yeni bölümler
5. **Danışman pazaryeri**: yönetici onay akışı var ama danışmana e-posta bildirimi yok;
   talep geldiğinde bildirim ve okunmamış sayacı eklenmeli.
6. **Kanıt dosyası paylaşımı**: Ekip paketi "paylaşılan ürün dosyaları" vadediyor ama
   `/api/dossiers` yalnızca kullanıcıya özel. Ekip/kuruluş kavramı gerekiyor.
7. **Değişiklik takibi bildirimi**: izleme listesi cihazda (localStorage) tutuluyor;
   sunucu tarafına taşınıp değişiklikte e-posta gönderilmeli.
8. **Genel mevzuat aramada boş tarih**: `gazette_date` çoğu kayıtta null; Bedesten'den
   RG tarihi çekilip listede gösterilmeli.
9. **Erişilebilirlik turu**: düğme kontrastları (turuncu üstü beyaz metin), odak sırası,
   `aria-live` bölgelerinin gerçekten duyurulup duyurulmadığı.

### P3 — Altyapı
10. Yerel geliştirme için `.env.example` içine `PUBLIC_BASE_URL=http://localhost:8000`
    notu ve `scripts/dev.sh` açıklaması README'ye eklenmeli.
11. `.claude/launch.json` sürüm kontrolünde değil (yalnız bu makinede); gerekirse
    `.gitignore`'a `.claude/` eklenmeli.
12. Playwright tabanlı görsel duman testi (`scratchpad/shoot.py` benzeri) `tests/`
    altına alınabilir; şu an yalnızca oturum içi kullanıldı.

## 2 Eylül 2026 (akşam) — kullanıcı gibi tam özellik turu
İki hesapla (müşteri + yönetici/danışman) her kontrol tıklandı. Çalıştığı doğrulananlar:
açılış sayfası etkileşimleri (ürün sekmeleri, aylık/yıllık, SSS), hızlı rotalar, kaynak /
belge türü / yıl / mülga filtreleri, sayfalama (26 sayfa ileri-geri), belge okuyucu (metin
içi arama ve vurgulama, atıf kopyalama, resmî bağlantılar, 300 bin karakterlik Gümrük
Kanunu'nda 112 bölümlük içindekiler), genel mevzuat başlık/içerik/numara modları ve tür +
tarih filtreleri, MCP adresi kopyalama, tema kalıcılığı, görsel yükleme (80×80 altı görsel
için açık hata), aday kod → tarife ağacı → dal seçimi, ön değerlendirme + takip sorusu +
uzman paketi indirme + kanıt dosyası kaydı, izleme listesine ekleme/kaldırma, değişiklik
defteri, işlem rehberi, danışman başvurusu → yönetici onayı → talep gönderme → kabul →
karşılıklı mesaj → kapatma, yönetici panelinde paket değişikliği, Hesabım'da kota, JSON
indirme (110 KB), dosya silme, güvenli çıkış, hesap silme, admin erişim kontrolü (303/403).

### Bu turda bulunan eksikler (plana eklendi)
- **Tarife doğrulama yarışı**: GTİP yazıp hemen "GTİP bul" düğmesine basınca "doğrulanmasını
  bekleyin" uyarısı çıkıyor; doğrulama bitince analiz kendiliğinden başlamalı (P1).
- **Vergi oranları maliyete akmıyor**: Tarife aracı %12 GV ve %39 İGV'yi buluyor ama ön
  değerlendirmede maliyet için kullanıcıdan aynı oranların elle "doğrulanmış" girilmesi
  isteniyor; "bulunan oranı kullan" düğmesi gerekli (P1).
- **Danışmanlık formu min. uzunluk**: konu 5, mesaj 10 karakter altında yalnızca tarayıcı
  balonu çıkıyor; alan altına görünür ipucu ve sayaç eklenmeli (P2).
- **Danışman bildirimi yok**: yeni talep yalnızca Danışmanlar sekmesi açılınca görünüyor;
  sekmede okunmamış rozeti ve e-posta gerekli (P2, mevcut madde 5 ile birleşti).
- **Kurumsal paket düğmesi pasif**: Hesabım › Paketler'de "Satış ekibiyle görüşün" tıklanamıyor;
  açılış sayfasındaki gibi mailto bağlantısı olmalı. Stripe kapalıyken "Stripe ayarı
  bekleniyor" yerine kullanıcıya anlamlı bir metin ("Yakında") gösterilmeli (P2).
- **404 sayfası**: bilinmeyen adresler düz metin "Not Found" döndürüyor; markalı 404 (P3).
- **Görsel boyut ipucu**: yükleme kutusunda 80×80 alt sınırı yazmıyor (P3).
- **Silinen kanıt dosyası kotayı iade etmiyor** (4/10 kalıyor); bilinçli tasarımsa Hesabım'da
  açıklanmalı (P3).
- **Kaynak filtre + belge türü + yıl** birlikte çoğu zaman 0 sonuç veriyor; boş sonuçta
  hangi filtrenin daralttığını gösteren "filtreyi kaldır" çipleri yararlı olur (P3).

## Önemli kimlikler / seçiciler
- Oturum çerezi: `tbm_session` (HMAC imzalı, `auth_service.GoogleAuthService`).
- Kapsam sekmeleri: `[data-scope=customs|ticaret|general]`; Gümrükçe alt sekmeleri
  `[data-customs-view=assistant|tariff|controls|changes|consultants|guide]`.
- Ön değerlendirme formu: `#customsQuestion #productDescription #originCountry
  #candidateGtip #composition #analyseButton`; sonuç `#customsOutput`, kaydet `#saveScenario`.
- Tarife: `#tariffForm #tariffGtip #tariffOrigin`; kontrol: `#controlsForm #controlsGtip`.
- Hesap diyaloğu: `#appAccountButton`, sekmeler `[data-account-tab=summary|dossiers|plans]`.

## Kararlar
- Tasarım yumuşatması "ek katman" olarak dosya sonuna yazıldı; mevcut kuralların üstüne
  yazılmadı ki fark tek blokta görülsün ve gerekirse tek hamlede geri alınsın.
- Yerel test için gerçek Google hesabı açılmadı; imzalı test çerezi kullanıldı.
