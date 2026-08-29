# Ticaret Bilgi Masası — Rekabet ve fiyatlandırma incelemesi

Tarih: 29 Ağustos 2026

Bu çalışma yalnız rakiplerin herkese açık resmî sayfalarında görülen özellik ve fiyatları kullanır. Teklif formunun arkasında kalan fiyatlar tahmin edilmemiştir.

## Rakip görünümü

| Ürün | Açık fiyat | Güçlü tarafı | Açık boşluğu |
|---|---:|---|---|
| [Mevzuat.Net](https://www.mevzuat.net/) | Mevzuat + vergi hesaplama 9.750 TL + KDV/yıl; 5 kullanıcı 23.500 TL + KDV/yıl ([abonelik](https://abonelik.mevzuat.net/)) | 1994'ten gelen marka, günlük haber, GTİP-menşe vergi ekranı, BTB ve takip listeleri | Görselden düzenlenebilir evsaf çıkarımı ve kaynaklı aday sınıflandırma akışı ana teklif değil; arayüz yoğun ve fiyat yıllık taahhütlü |
| [Gümrük.com.tr](https://xn--gmrk-0rac.com.tr/) | 1 kullanıcı 560 TL KDV dahil/yıl; 2 kullanıcı 750 TL/yıl ([paketler](https://xn--gmrk-0rac.com.tr/fiyatlar)) | Çok düşük fiyat, GTİP/BTB/rejim/mevzuat tek pakette | Yapay zekâ ürün dosyası, maliyet senaryosu, kaynak kanıt zinciri, TAREKS açıklaması ve MCP/API görünmüyor |
| [Mevbank Neo](https://lebibyalkin.com.tr/mevbank-neo/tum-mevzuat) | Teklif usulü | Milyonlarca belge, uzman açıklaması, içtihat/özelge, bülten ve çoklu kullanıcı | Gümrük ön maliyet ve fotoğraftan ürün sınıflandırma odaklı değil; fiyat şeffaf değil |
| [MAVİ Mevzuat](https://gumrukmevzuati.net/) | Teklif usulü | Günlük haber, tasarruflu yazılar, gümrük ERP ekosistemi | Bağımsız satın alan KOBİ için fiyat şeffaf değil; AI ön değerlendirme ve resmî kanıtlı maliyet akışı görünmüyor |
| [Ticaret Bakanlığı Gümrük Rehberi](https://gumrukrehberi.gov.tr/anasayfa) | Ücretsiz | Birincil resmî ve anlaşılır temel rehber | İşlem/ürün bazında aday GTİP, toplu canlı mevzuat analizi, değişiklik alarmı ve maliyet dosyası değil |
| [CodeHTS](https://codehts.com/pricing) | Ücretsiz; Pro yıllık ödemede 16,08 USD/ay | Global AI sınıflandırma, dosya yükleme, alarm, rapor, ekip ve entegrasyon vizyonu | Türkiye'nin 12 haneli GTİP/İGV/TAREKS uygulamasına özgü değil |
| [CustomsAI](https://customscity.com/customsai-hts-classification/) | 10 işlem ücretsiz; 49/99/299 USD/ay | Hacim bazlı net fiyat, adaylar ve güven puanı, yüksek işlem kapasitesi | Türkiye mevzuatı ve yerel kontrol/vergiler yerine Kuzey Amerika ağırlıklı |
| [TariffTel TTExplore](https://www.tarifftel.com/ttexplore/) | Tek sınıflandırma 7 GBP; paketlerde daha düşük | Üç aday, güven ve gerekçe; uzman doğrulamalı üst paket | Fotoğraftan sınıflandırma yok; TTVerified 299 GBP/aydan başlıyor ve Türkiye odaklı değil |

## Bizim mevcut artılarımız

- Türkiye odaklı tek akışta fotoğraf → düzenlenebilir evsaf → üç aday kod → menşe → İGV/rejim → TAREKS/TSE/kontrol → maliyet dosyası.
- Resmî kaynak kimliği, tarih, satır/sayfa ve arşiv SHA-256 bilgisiyle kanıt zinciri.
- Resmî Gazete/Adalet güncel katmanı saatlik; tam Ticaret Bakanlığı kataloğu altı saatlik yenileniyor.
- Gümrük, ithalat, ihracat, devlet desteği, pazar raporu, müşavirlik adresi ve genel mevzuatı aynı sistemde arama.
- ChatGPT/Codex ve kurumsal uygulamalar için MCP erişimi.
- Fotoğrafın tek başına kesin GTİP sayılmadığı, eksik özelliklerin kullanıcıdan istendiği insan-onaylı güvenli akış.

## Şu anki eksiklerimiz

- Uzman tarafından doğrulanmış/kaşelenmiş sınıflandırma hizmeti ve BTB başvuru iş akışı yok.
- Kullanıcı hesabı, sunucu tarafında ürün dosyası geçmişi, ekip/rol yönetimi ve denetlenebilir aktivite kaydı henüz yok.
- PDF müşavir devir dosyası, Excel toplu ürün yükleme ve ERP/e-ticaret bağlantıları tamamlanmadı.
- Ödeme, kota ve abonelik yönetimi yok; fiyat kartları satış vaadi değil erken erişim konumlandırması olmalı.
- Kullanıcıya özel GTİP/mevzuat değişiklik bildirimleri ve e-posta alarmı yok.
- AB EBTI görsel hakları netleşmeden toplu görsel eğitim/veri ürünü yapılamaz.
- Sonuç doğruluğunu ölçen, gümrük müşaviri tarafından etiketlenmiş Türkiye test seti ve yayımlanabilir başarı metriği henüz yok.

## Önerilen lansman fiyatı

| Plan | Aylık | Yıllık | Konum |
|---|---:|---:|---|
| Başlangıç | 0 TL | 0 TL | Kaynak arama, sınırlı ürün analizi ve ürün dosyası; müşteri edinme |
| Uzman | 790 TL + KDV | 7.900 TL + KDV | Tek kullanıcı; Mevzuat.Net'in birleşik paketinin altında, AI maliyetini karşılayan ana plan |
| Ekip | 2.490 TL + KDV | 24.900 TL + KDV | 5 kullanıcı, ortak dosya/izleme, daha yüksek analiz kotası ve raporlar |
| Kurumsal | 7.500 TL + KDV'den başlayan | Teklif | MCP/API, özel kota, rol, kayıt/audit, SLA ve kuruma özel kaynak |

Fiyat mantığı: 560 TL/yıllık düşük maliyetli veri tabanı ile fiyat yarışına girilmemeli. Ana kıyas, 9.750 TL + KDV/yıllık Mevzuat.Net birleşik paketi ile 49 USD/aydan başlayan global AI sınıflandırma ürünleridir. Uzman planı yıllık alımda yerel güçlü rakibin altında kalırken görsel analiz ve Türkiye kontrol zinciri için yeterli fark bırakır.

## Yayına almadan önce ticari eşikler

1. Ücretsiz/Uzman/Ekip kotaları sunucu tarafında uygulanmalı.
2. Her analiz için gerçek OpenRouter maliyeti ve başarısız fallback oranı ölçülmeli.
3. En az 200 ürünlük uzman doğrulamalı test setinde ilk 3 aday başarısı raporlanmalı.
4. Ödeme, fatura, KVKK/açık rıza, hesap silme ve veri saklama politikası tamamlanmalı.
5. “Kesin GTİP” yerine aday kod ve resmî/uzman doğrulama ayrımı tüm satış metinlerinde korunmalı.
