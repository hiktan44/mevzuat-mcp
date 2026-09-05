# Gümrük Müşaviri Gözüyle Uçtan Uca Test Raporu — 5 Eylül 2026

Bu rapor, uygulamanın bir gümrük müşaviri gibi kullanılmasıyla (web arayüzü, JSON API ve 44 MCP aracı)
tespit edilen hataları ve eksikleri toplar. Hiçbir uygulama kodu değiştirilmedi; bulgular dosya ve satır
numarasıyla verilir, çoğu küçük bir betikle yeniden üretilebilir.

## Nasıl test edildi

- 114 birim testi geçti (`pytest`).
- Test ortamında ticaret.gov.tr, Bedesten, mevzuat.gov.tr ve AB kaynaklarına dışarı erişim yoktu (proxy 403).
  Bu yüzden tarife (İRK + İGV) ve kontrol tebliği veritabanları gerçekçi örnek satırlarla yerelde dolduruldu
  (porselen 6911.10, pantolon 6103.42, telefon 8517.13, dizüstü 8471.30, domates 0702, çelik profil 7216.10, bira 2203).
- Playwright ile masaüstü (1440) ve mobil (390) genişlikte Gümrükçe'ye Sor'un altı sekmesi, tarife/maliyet, menşe
  senaryoları, kontrol sorgusu, değişiklik defteri, izleme listesi ve anahtarsız ön değerlendirme gezildi.
- İmzalı oturum çerezi üretilerek hesap, kanıt dosyası, e-posta, fatura, CSRF ve yönetici erişim uçları denendi.
- MCP istemcisiyle 44 araç listelendi; çevrim dışı çalışabilen 13 araç çağrıldı.
- Üç ayrı derin kod incelemesi (tarife/menşe, kontrol/danışman motoru, web arayüzü) yapıldı.

## Çalıştığı doğrulananlar

Tarife sorgusu (noktalı 6911.10.00.00.11 dahil), 8 haneli kodda alt satır ayrışması uyarısı, dipnotlu satırın
otomatik hesaptan dışlanması, GTS sektör istisnası (Hindistan/tekstil), gözetim kıymeti yükseltmesi, KKDF ödeme
şekli önerisi, tam girdiyle "complete" maliyet (11.250 USD kıymet, 7.215 USD toplam vergi), "hariç" satırının
tebliğ kapsamını bastırması, snapshot farkı üretimi (9 satır farkı), SSRF koruması (http/özel IP reddi), CSRF
kaynak denetimi (evil origin 403), yönetici erişim kontrolü (403/303), mobilde yatay kaydırma olmaması, XSS
(tüm `innerHTML` noktaları kaçırılıyor).

## KRİTİK — yanlış vergi veya yanlış kapsam üretir

1. ✅ DÜZELTİLDİ (5 Eyl) — **Menşe sütunu süreçten sürece değişiyor (belirlenimsiz).** `tariff_engine.py:707-712` `_matching_group`
   `labels` kümesi üzerinde dolaşıyor; I/IV sayılı liste ve İGV Ek-2/3 etiketlerinde birden çok etiket "AB"/"EFTA"
   içerdiğinden `PYTHONHASHSEED=0` ile Almanya → `EFTA/F.ADA` (EMY sütunu), `PYTHONHASHSEED=1` ile `AB/BK` çıkıyor.
   Aynı sorgu iki dağıtımda farklı oran verir. Düzeltme: `sorted(labels)` + açık öncelik tablosu.
2. ✅ DÜZELTİLDİ (5 Eyl) — **STA ülkeleri AB sütununa yapıştırılıyor.** Aynı fonksiyon, `"1"` etiketi olmayan tablolarda Güney Kore,
   Malezya, Singapur, Kosova, Fas, Tunus, Mısır, İsrail, Şili… için kendi sütunları varken `AB/...` sütununu
   seçiyor. Tarım ürünlerinde (I sayılı liste) bu ülkelerin taviz sütunu yoktur; Fas menşeli domates için "%0"
   üretmek doğrudan yanlış vergidir. `_EXPLICIT_LABELS` hiç sıraya gelmiyor.
3. ✅ DÜZELTİLDİ (5 Eyl) — **IV sayılı liste V sayılı liste olarak okunuyor.** `tariff_engine.py:452` `"v say" in file_key` kontrolü
   `"iv say"` kontrolünden önce geldiği için `IV SAYILI LİSTE.xlsx` → "V Sayılı Liste" (doğrulandı). Balık ve su
   ürünlerinin GV sütunları ve EFTA/Faroe EMY sütunu hiç yazılmıyor; yerine "askıya alma" satırı üretiliyor.
4. ✅ DÜZELTİLDİ (5 Eyl) — **İGV Ek-2/Ek-3 sayfaları sessizce atlanıyor.** `tariff_engine.py:442-447` sayfa adında `"ek 2"` (boşluklu)
   arıyor; sayfa `EK-2` ise sonuç boş (doğrulandı). Tarım/işlenmiş tarım İGV'si "yok" görünür.
5. ✅ DÜZELTİLDİ (5 Eyl) — **A.TR ile gelen üçüncü ülke menşeli eşya uyarısı yok.** Almanya → İGV %0 koşulsuz veriliyor ve maliyete
   otomatik alınıyor (`calculate`, `tariff_engine.py:1077`). Tedarikçi beyanı/menşe şahadetnamesi yoksa İGV ve
   EMY menşe (ya da DÜ) sütunundan alınır. `CustomsInquiry.dispatch_country` tanımlı ama hiçbir yerde okunmuyor;
   "tedarikçi beyanı" ifadesi depoda geçmiyor. Müşavirin en sık düzelttiği hata budur.
6. ✅ DÜZELTİLDİ (5 Eyl) — **Menşe belgesi kuralı fasıla bakmıyor.** `origin_documents.py:138` yalnız ülke alıyor: AB'den domates (fasıl
   07) ve AKÇT çelik (7216) için A.TR öneriliyor; doğrusu EUR.1/menşe beyanı. Birleşik Krallık, G.Kore,
   Singapur için "EUR.1" deniyor; bu anlaşmalarda EUR.1 yoktur (fatura üzeri menşe beyanı). Testler yanlışı
   kilitliyor (`tests/test_origin_documents.py:21-25`).
7. ✅ DÜZELTİLDİ (5 Eyl) — **Kontrol tebliği keşfi alt dize eşleşmesiyle yanlış tebliği indeksliyor.** `control_engine.py:483`
   `_key("2026/1") in _key("... 2026/12)")` → True (doğrulandı). 2026/1 (TSE) listesi 2026/12-19 metniyle,
   2026/2 → 2026/20-25, 2026/3 → 2026/31-35 ile üzerine yazılabilir; TSE kapsamındaki ürün "kapsam dışı" çıkar.
8. ✅ DÜZELTİLDİ (5 Eyl, mekanizma) — **Çok ekli tebliğlerde yalnız tek Ek indeksleniyor.** `control_engine.py:192-219` en yoğun tek "Ek-N"
   bölümünü alıyor. 2026/5 Tarım (Ek-1/A…), 2026/19 (Ek-1 tütün, Ek-2 alkol), 2026/3 ve 2026/6 (Ek-2 **ithali
   yasak**), 2026/20 Sağlık, 2026/23 hurda listelerinin kalan ekleri kaybolur → yanlış negatif.
9. ✅ DÜZELTİLDİ (5 Eyl) — **Kullanıcı oranı resmî oranı sessizce eziyor.** `/api/tariff/cost` gövdesinde `customs_duty_rate: 0`
   gönderilince Çin porselen için resmî %12 yerine 0 kabul ediliyor, uyarı yok (`tariff_engine.py:1075-1083`).
   Ayrıca `LandedCostInput` bilinmeyen alanı yutuyor (`customs_duty_rat` yazım hatası → resmî oran otomatik girer).

## YÜKSEK — kullanıcı hemen fark eder

10. **Tarife & Maliyet sekmesi hiçbir zaman toplam vermiyor.** Form yalnız fatura/navlun/sigorta/KDV/ödeme
    gönderiyor (`web/app.js:2158`); damping, ÖTV, gözetim, EMY ve miktar alanı yok → `landed_total` daima
    "Oran eksik". `cost.missing_rates` ve `unit_landed_cost` ekranda hiç basılmıyor. Tam girdiyle API "complete"
    dönüyor; sorun arayüzde.
11. **EMY her hesabı "partial" bırakıyor.** IV sayılı liste dışındaki her GTİP'te `additional_financial_liability`
    satırı olmadığından kullanıcı elle "0" girmezse toplam çıkmıyor; İGV listesinde satır olmaması da "İGV
    uygulanmıyor (%0)" yerine "oran eksik"/"kod başına değişiyor" (`web/app.js:2181`) olarak gösteriliyor.
12. **MCP `calculate_import_landed_cost` web API'nin gerisinde.** `payment_method`,
    `additional_financial_liability_rate`, `customs_duty_rate`/`additional_duty_rate` parametreleri yok
    (`mevzuat_mcp_server.py:2643-2660`); MCP'den KKDF önerisi alınamıyor ve toplam hiç tamamlanamıyor.
    `resolve_turkish_tariff_tree` 4 haneli pozisyonu (6911) reddediyor.
13. ✅ DÜZELTİLDİ (5 Eyl, uyarı + İngilizce ad desteği) — **Tanınmayan menşe sessizce "Diğer Ülkeler".** "Germany", "Almanyaa", "Çin Halk Cumhuriyeti" → sütun 7,
    `status=matched`, uyarı yok. GTS metadata'daki "Çin Halk Cumhuriyeti" anahtarı kullanıcının "Çin" girdisiyle
    eşleşmiyor. Ukrayna, İran/TPS-OIC/D-8 üyeleri de sütunsuz DÜ'ye düşüyor; Ukrayna STA yürürlüğü doğrulanmalı.
14. **Kullanılmış eşya ve sevk ülkesi ön değerlendirmeye girmiyor.** "Almanya'dan sevk, Çin menşeli kullanılmış
    CNC" senaryosunda çıktıda kullanılmış eşya izni (İthalat Tebliği 2026/9), A.TR/İGV ilişkisi ve makine tebliği
    (2026/32) yok; `condition=used` yalnız uzman paketine tek cümle ekliyor (`customs_advisor.py:1015`).
15. **6/8/10 haneli seçimde kontrol kanıtı hiç üretilmiyor** (`customs_advisor.py:1164-1170`); motor prefiks
    satırlarını tuttuğu hâlde "olası kapsam" taraması yapılmıyor.
16. **Tek tebliğ bile indekslenemezse bütün kontrol sistemi "unavailable"** (`control_engine.py:735,744`);
    başarısız eşitlemede 3 saat bekleniyor. Tarife tarafında da bir arşiv inmezse her `lookup` tam arşiv
    indirmeyi tetikliyor (`tariff_engine.py:818, 645`) → dakikalarca askıda istek ve Bakanlık sunucusuna yük.
17. **Kapı bayrakları istemciden geliyor.** `tariff_selection_confirmed`, `exact_gtip_confirmed`,
    `classification_confidence_score` düz istek alanı (`customs_advisor.py:88-157`); herhangi bir API/MCP
    istemcisi "doğrulandı" diyerek risk seviyesini düşürebilir. Sunucu `tariff_lookup` sonucuna göre türetmeli.
18. **Görsel yükü redaksiyondan geçiyor.** `customs_advisor.py:649` `redact_data` base64 görsele de uygulanıyor;
    11 haneli rakam dizisi `[TCKN_GİZLENDİ]`, telefon deseni `[TELEFON_GİZLENDİ]` ile değiştiriliyor
    (doğrulandı) → data URL bozulur, bütün model zinciri aynı bozuk yükle düşer.
19. **25 MP sınırı görsel tamamen çözüldükten sonra uygulanıyor** (`customs_advisor.py:521-528`); 8 MB'lık
    13000×13000 PNG yüzlerce MB RAM tüketir. `Content-Length` yoksa gövde sınırsız okunuyor (`app.py:1207`).
20. **Danışman sekmesi açılamıyor.** `marketplace-enabled` sınıfı yalnız `loadConsultants()` içinde
    (`web/app.js:1802`) ekleniyor; o da yalnız gizli sekmeye tıklanınca çağrılıyor. `CONSULTANTS_MARKETPLACE_ENABLED=1`
    olsa bile sekme görünmez.
21. **PDF olarak kaydet çok sayfalı dosyayı ilk sayfaya kırpıyor** (`web/app.css:958-964`, `inset:0`); kapalı
    `details` bölümleri PDF'e girmiyor.
22. **`localStorage` üst düzeyde try/catch'siz** (`web/app.js:2398`); depolama engelliyse uygulama hiç açılmıyor.
23. **Tarife doğrulama / analiz yarışı kilitlenebiliyor** (`web/app.js:1740`): ağaç "matched" değilse
    `pendingSubmit` sonsuza dek bekler.
24. **"Bu cihazda kayıtlı ön değerlendirmeler" paneli ölü**; `gumrukce-scenarios` anahtarı hiç yazılmıyor.
25. **Gözetim için miktar birimi yok** (adet/kg/çift/m²); `quantity` hem gözetim çarpanı hem birim maliyet böleni.
26. **Sayı girişi Türkçe biçimi yutuyor**: "1.234,56" → `null`, fatura yok sayılıyor; API "TL" para birimini
    reddediyor (TRY olmalı, seçici yok).

## ORTA

27. Tarih hücreleri GTİP sanılıyor: `_normalise_gtip("01.01.2026")` → `01012026`, "31.12.2025" → `3112`
    kontrol satırı (`control_engine.py:137-189`, `tariff_engine.py:542`) → yanlış pozitif kapsam.
28. 11 haneli kullanıcı girdisi başa sıfır eklenerek başka fasıla taşınıyor: `69111000001` → `069111000001`.
29. "hariç" tespiti parantez dengesine bağlı; dengesiz parantez tüm tebliğin pozitif eşleşmelerini bastırıyor;
    aynı tebliğde 6103 ve 610342 satırları iki ayrı eşleşme olarak listeleniyor (yinelenen kart).
30. Yetkili kurum sezgiseli yanlış: tıbbi cihaz → "Sağlık Bakanlığı" (TAREKS/Ticaret olmalı), tütün-alkol →
    "Ticaret" (Tarım ve Orman olmalı). `control_sources.json`'a açık `authority/system` alanı eklenmeli.
31. Hakem modelin oyu bağımsız oy gibi sayılıyor (`customs_advisor.py:1397-1423`) → güven "high" çıkabilir.
32. Tarife tablosu eşitlenmemişken sınıflandırma "aday üretilemedi" diyor; gerçek neden "tablo yok".
33. Model çıktısı şema hatası kullanıcıya 422 "İstek doğrulanamadı" olarak dönüyor (502 olmalı).
34. Damping yalnız sabit tutar, ÖTV yalnız tutar; damping çoğunlukla CIF % veya USD/kg, ÖTV ad valorem
    matrahı (kıymet + GV + diğer vergiler). Kullanıcı elle hesaplıyor.
35. Para birimi karışıyor: USD gözetim kıymeti EUR faturayla `max()` karşılaştırılıyor; TCMB kuru ve TL
    beyanname özeti yok. "Sabit işlem harcı" ifadesi mevzuatta yok; doğrusu beyanname damga vergisi.
36. KKDF: "peşin (kredi kartı)" → `kredi` belirteci yüzünden %6; vadeli navlun/sigorta matrah seçeneği yok;
    2015/7511 KKDF %0 GTİP listesi yok.
37. Ön değerlendirme maliyet tablosu `deterministic_cost`'un yarısını göstermiyor (KKDF uyarısı, missing_rates).
38. Değişiklikler sekmesi yalnız fark sayısını basıyor; satırlar (`gtip/before/after`) gösterilmiyor, izleme
    listesi fiilen çalışmıyor; `value.message` API'de yok.
39. `changes()` aktiflik durumuna bakmıyor, `rate_text` biçim değişimini fark sayıyor, `valid_from` sabit.
40. `lookup` prefiks sorgusu `LIKE` ile tam tarama; karar ağacı N+1; `matched_gtips[:500]` kesmesi çocukları
    eksiltebilir.
41. SSRF: DNS-rebinding (TOCTOU), gövde tamamen belleğe, PDF/görsel işleme senkron (event loop bloke).
42. Model çıktısındaki oranlar `tariff_lookup.unambiguous_rates` ile sunucuda karşılaştırılmıyor.
43. `as_of_date` alınıyor ama kullanılmıyor (geçmiş tarihli beyan için oran seçilemiyor).
44. Mobil: "Gümrükçe'ye Sor" sekmesi iki satıra bölünüyor, 6 alt sekme kesiliyor; kanıt tabloları sarmalayıcısız.
45. `#query maxlength=300` ama `/api/search` 200 karakter sınırı → 422.
46. Erişilebilirlik: sekmelerde `aria-selected`/`role=tab` yok; süreç göstergesi (`.customs-flow`) hiç
    güncellenmiyor; `#customsResult aria-live` tüm dosyayı okutuyor.

## DÜŞÜK

47. README "44 farklı tool" (satır 14) ve "43 araç" (satır 379) çelişiyor; landing'de iki farklı iletişim adresi.
48. `X-Forwarded-For` ilk değeri güvenilir kabul ediliyor; rate limiter sözlüğü hiç budanmıyor;
    `/api/controls/lookup` ve `/api/classification/evidence` `_trusted_request_origin` çağırmıyor.
49. Senaryo ucu yinelenen menşeleri ayıklamıyor; `origins` uzunluk sınırı yok.
50. "Bu oranları kullan" navlunu `"0"` ile eziyor (`web/app.js:2137`); `#tariffPayment` seçimi
    `#paymentMethod`'a taşınmıyor.
51. E-posta düğmesi yapılandırma bilgisi olmadan gösteriliyor (tıklayınca 503).
52. Abonelik durumu ham İngilizce ("active") basılıyor; para tutarları iki ondalıksız.
53. `_docx_text` tanımlı ama çağrılmıyor; dipnot metni ingest edilmiyor (yalnız "(1)" işareti).
54. `_ATR_ORIGIN_NOTE` kullanılmıyor; "içindetay" yazım hatası; `kibris` girdisi KKTC ile karışıyor.
55. `control_engine._connect` bağlantıları kapatılmıyor (tanıtıcı sızıntısı).

## Bir müşavirin bekleyip bulamayacağı özellikler

- Menşe ↔ sevk/çıkış ülkesi ayrımı; A.TR + tedarikçi beyanı/menşe şahadetnamesi koşulu; fasıl bazlı A.TR /
  EUR.1 / menşe beyanı / AKÇT kuralı; onaylanmış ihracatçı ve fatura beyanı eşikleri.
- GTİP'e özgü gözetim, tarife kontenjanı, damping/sübvansiyon (menşe + üretici), korunma önlemi tabloları
  (bugün hepsi `not_integrated`; LLM'e giden "kanıt" genel sayfa metni).
- GTİP bazlı KDV oranı (I/II sayılı liste) ve ÖTV listesi tespiti; TRT bandrolü, GEKAP, beyanname damga vergisi,
  ardiye/liman gibi tescil öncesi giderler ayrı satır olarak.
- İthalat Tebliğleri indeksi: kullanılmış/yenileştirilmiş eşya (2026/9), ozon (2026/14), yasak/izne tabi eşya;
  ÜGD eklerinin "kapsam / yasak / muaf" ayrımı.
- TCMB kuru ile TL beyanname özeti; beyanname tescil tarihine göre snapshot seçimi.
- Toplu hesap (Excel/CSV ile çok satırlı beyanname), Excel/CSV dışa aktarım, panoya kopyalama.
- Kanonik ülke listesi (ISO kodu, TR/EN ad) ve seçici; Türkçe sayı biçimi girişi.
- İzleme listesinin sunucuda tutulması ve değişiklikte e-posta; danışman e-posta bildirimi.
- Ekip paketinde vadedilen paylaşılan kanıt dosyaları (ekip/kuruluş kavramı yok).
- Zorunlu belge listesinin yapılandırılmış satırlara dönüştürülmesi (muafiyet, numune, sanayici istisnası).
- Test kapsamı: I/III/IV listeleri, İGV Ek-2/3, `_group_map` ad çakışması, hash-seed belirlenimciliği,
  `_discover_documents`, çok ekli tebliğ, `calculate` entegrasyonu, `changes`, kullanıcı-oran çakışması.

## Önerilen sıra

1. Kritik 1-4 ve 7-8 (motor yanlış oran/kapsam üretmesin): sıralı öncelik tablosu, `_group_map` sırası,
   sayfa adı regex'i, tebliğ kodu regex'i, çok ek desteği; her biri için birim test.
2. Kritik 5-6 ve 9: sevk ülkesi + menşe ispatı bayrağı, fasıl bazlı belge kuralı, ülke listesi tek kaynak,
   kullanıcı-oran çakışmasında uyarı, `extra="forbid"`.
3. Yüksek 10-12: Tarife & Maliyet formuna eksik alanlar, "İGV listesinde yok → %0" mantığı, MCP parametreleri.
4. Yüksek 17-19: sunucu tarafı doğrulama, görsel redaksiyon atlaması, görsel boyut kontrolü sırası.
5. Arayüz: danışman sekmesi, PDF, localStorage, yarış, mobil sekmeler, sayı biçimi.

## Düzeltme günlüğü

### 5 Eylül 2026 — 1. sıra (kritik motor hataları) kapatıldı; 126 test geçiyor

- `tariff_engine._matching_group`: etiketler sıralı geziliyor, ülke adı yalnız bütün sütun belirteciyle
  (`AB`, `EFTA`, `G.KORE`, `B-HER`, `BK`, `F.ADA`…) eşleşiyor; ülkenin kendi sütunu paylaşılan AB/EFTA
  sütununa göre önce geliyor; sorgulanan listede sütunu olmayan STA ülkesi uyarıyla "Diğer Ülkeler"e düşüyor.
  Sütun seçimi artık (GTİP, snapshot, ölçü türü) başına yapılıyor; IV sayılı listede GV ve EMY sütunu aynı anda
  "primary" olabiliyor (bulgu 1, 2 ve rapordaki yüksek öncelikli 8 numaralı sütun-çakışması).
- `tariff_engine._group_map`: Romen rakamlı liste adları kelime sınırıyla ve uzun addan kısaya doğru
  eşleşiyor (`VII → VI → IV → V`); İGV Ek-2/Ek-3 sayfa adları `EK-2`, `Ek 2`, `EK2` biçimlerini kabul ediyor.
- `control_engine.communique_code_matches`: tebliğ numarası iki yanı sınırlı tam eşleşmeyle aranıyor;
  aynı koda ikinci bir belge düşerse hata kaydediliyor, ilk belge korunuyor.
- `control_engine.extract_annex_scope`: aynı ekin bütün parçaları (`Ek-1/A`, `Ek-1/B`…) birleştiriliyor;
  gövde içindeki "Ek-1'de", "Ek-1 sayılı listede" atıfları başlık sayılmıyor. `control_sources.json`'a
  `scope_annexes: [1, {"annex": 2, "kind": "prohibited"}]` biçiminde çok ek ve **ithali yasak** listesi
  tanımı eklenebiliyor; `control_scope` tablosu `list_kind` sütunu ve yeni birincil anahtarla otomatik
  taşınıyor; sorgu sonucunda yasak liste eşleşmesi ayrı değerlendirmeyle dönüyor.
  Hangi tebliğin hangi ekinin yasak listesi olduğu bu ortamdan (resmî metinlere erişim yok) doğrulanamadığı
  için `control_sources.json`'da henüz `prohibited` tanımı yapılmadı; resmî metin teyidiyle eklenmelidir.
- Kalan kritikler: 5 (A.TR + üçüncü ülke menşe uyarısı), 6 (fasıl bazlı menşe belgesi), 9 (kullanıcı oranı
  resmî oranı eziyor) — raporun 2. sırası.

### 5 Eylül 2026 — 2. sıra kapatıldı; 142 test geçiyor

- `countries.py`: tarife motoru ve menşe belgesi modülünün ortak ülke kayıt defteri (94 ülke; Türkçe/İngilizce
  ad, ISO kodu, rejim, sütun-1 üyeliği, kendi sütun belirteci, anlaşmanın menşe ispat belgesi). Şili, Tunus,
  İsrail, Venezuela STA listesine alındı; Ukrayna/Ürdün/Lübnan/Japonya/Peru/Kolombiya "yürürlükte değil"
  uyarısıyla işaretli. Tanınmayan ülke adı artık uyarı veriyor (`origin_recognised=false`); "Germany",
  "Çin Halk Cumhuriyeti" gibi girdiler çözümleniyor. İki liste arasındaki tutarsızlık testle kilitlendi.
- `origin_documents.py`: belge kuralı fasıl ve sevk ülkesine bakıyor. AB'den 1-24. fasıl temel tarım ürünü →
  EUR.1/EUR-MED (1/98 OKK); AKÇT kömür-çelik (2601, 2701-2704, 7201-7229, 7301-7302) → EUR.1; sanayi ve 1/95
  Ek-1 işlenmiş tarım ürünü → A.TR + tedarikçi beyanı. Birleşik Krallık, G.Kore, Singapur → menşe beyanı;
  Malezya, BAE, Katar, Venezuela, İran → anlaşmaya özgü belge. AB'den sevk edilen üçüncü ülke menşeli eşyada
  A.TR "gümrük vergisini kaldırır, İGV/EMY'yi kaldırmaz" satırı ekleniyor.
- `tariff_engine.lookup(..., dispatch_country=)`: sevk ülkesi AB ve eşya A.TR'ye uygunsa gümrük vergisi AB
  sütunundan (`atr_free_circulation=true`, A.TR ibrazına bağlı uyarısı), İGV/EMY menşe sütunundan. Menşe
  AB/EFTA/STA iken İGV/EMY tercihi `origin_proof_required` + `fallback_rates` (tevsik yoksa "Diğer Ülkeler"
  oranı) ile işaretleniyor.
- `tariff_engine.calculate`: kullanıcı oranı resmî orandan farklıysa `rate_overrides` ve uyarı;
  `LandedCostInput` bilinmeyen alanı reddediyor (`extra="forbid"`, yazım hatası 422).
- API/MCP/arayüz: `/api/tariff/lookup|cost|scenarios` ve MCP `lookup_tariff_measures`,
  `calculate_import_landed_cost` `dispatch_country` alıyor; MCP maliyet aracına `payment_method`, EMY ve
  doğrulanmış oran parametreleri eklendi (bulgu 12'nin parametre kısmı). Tarife & Maliyet formuna "Sevk ülkesi"
  alanı; senaryo tablosunda A.TR / menşe tevsiki notları; ön değerlendirme sevk ülkesini kullanıyor.
- Kalan: bulgu 12'deki 4 haneli karar ağacı, bulgu 10-11 (arayüz toplamı/EMY-İGV yokluğu %0), 14-26.
