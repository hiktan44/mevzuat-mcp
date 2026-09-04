# Türkiye Mevzuat ve Ticaret Bakanlığı Bilgi MCP Sunucusu

Bu proje; Adalet Bakanlığı Mevzuat Bilgi Sistemi, Bedesten Mevzuat servisi ve Ticaret Bakanlığının resmî bilgi kaynaklarını tek bir [FastMCP](https://gofastmcp.com/) sunucusunda birleştirir. Kanun, karar, yönetmelik ve tebliğlerin yanında gümrük, ithalat-ihracat, devlet destekleri, istatistikler, yayınlar, ülke-pazar raporları ve ticaret müşavirliği/ataşeliği bilgileri ChatGPT, Codex ve diğer MCP istemcilerince aranabilir ve analiz edilebilir.

<a href="https://glama.ai/mcp/servers/@saidsurucu/mevzuat-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@saidsurucu/mevzuat-mcp/badge" alt="Mevzuat MCP server" />
</a>

![örnek](./ornek.png)

🎯 **Temel Özellikler**

* Adalet Bakanlığı Mevzuat Bilgi Sistemi'ne programatik erişim için standart bir MCP arayüzü.
* **44 farklı tool** ile kapsamlı mevzuat, tarife ve Ticaret Bakanlığı bilgi erişimi (üç resmî kaynak ailesi):
    * **mevzuat.gov.tr** üzerinden 21 araç (türe özel arama ve içerik)
    * **bedesten.adalet.gov.tr** üzerinden 5 araç (birleşik arama, gerekçe, içindekiler)
    * **ticaret.gov.tr** ve bağlı resmî alt alanlardan 18 araç (canlı katalog, belge okuma, resmî tarife/İGV, maliyet, ürün kontrol tebliğleri, ürün fotoğrafı evsaf çıkarımı ve gümrük ön değerlendirme kanıtı)
* Desteklenen 12 mevzuat türü:
    * **Kanun** - Türkiye Cumhuriyeti kanunları
    * **KHK** - Kanun Hükmünde Kararnameler
    * **Tüzük** - Tüzükler
    * **Kurum Yönetmeliği** - Kurum ve kuruluş yönetmelikleri
    * **Üniversite Yönetmeliği** - Üniversite yönetmelikleri
    * **Cumhurbaşkanlığı Kararnamesi** - Cumhurbaşkanlığı kararnameleri
    * **Cumhurbaşkanı Kararı** - Cumhurbaşkanı kararları
    * **CB Yönetmeliği** - Cumhurbaşkanlığı ve Bakanlar Kurulu yönetmelikleri
    * **CB Genelgesi** - Cumhurbaşkanlığı genelgeleri
    * **Bakanlar Kurulu Yönetmeliği** - Bakanlar Kurulu yönetmelikleri
    * **Tebliğ** - Tebliğler
    * **Mülga Mevzuat** - Yürürlükten kaldırılmış mevzuat
* **mevzuat.gov.tr araçları (21 tool)**: Her mevzuat türü için çift tool yapısı:
    * **Arama tool'u**: Başlık ve içerikte arama, Boolean operatörler (AND, OR, NOT), tarih filtreleme
    * **İçinde arama tool'u**: Madde bazında arama (keyword + semantik), alakalılık skoru ile sıralama
* **bedesten.adalet.gov.tr araçları (5 tool)**: Tüm mevzuat türlerini tek araçla kapsar:
    * **`search_mevzuat`**: 12 türde birleşik arama (başlık, içerik, numara, RG tarihi/sayısı filtreleme)
    * **`get_mevzuat_content`**: Tam metin getirme
    * **`search_within_mevzuat`**: Madde bazında anahtar kelime araması
    * **`get_mevzuat_gerekce`**: Kanun gerekçesi (amaç, komisyon raporları, madde gerekçeleri)
    * **`get_mevzuat_madde_tree`**: İçindekiler / madde ağacı (bölüm-madde hiyerarşisi)
* **Semantik Arama**: Tüm 9 `search_within_*` aracında `semantic=True` parametresi ile doğal dilde anlam tabanlı arama. OpenRouter API üzerinden embedding modelleri kullanır.
* Gelişmiş özellikler:
    * PDF'leri Mistral OCR ile metin çıkarma (CB Kararı ve CB Genelgesi için)
    * HTML'den Markdown'a otomatik dönüştürme
    * In-memory caching (1 saat TTL) ile hızlı erişim
    * Boolean arama operatörleri (AND, OR, NOT)
    * Tam cümle araması (exact phrase)
    * Tarih aralığı filtreleme
* Claude Desktop ve 5ire gibi MCP istemcileri ile kolay entegrasyon

## Ticaret Bakanlığı bilgi katmanları

Kaynak listesi `ticaret_sources.json` dosyasında ayrı ve elle düzenlenebilir tutulur; başlıklar, sektörler, ülke adları ve belge bilgileri canlı sayfalardan dinamik olarak çıkarılır. Gümrük, ithalat, ihracat, destekler ve İthalat Genel Müdürlüğü duyuruları saatlik; bütün katalog altı saatte bir yenilenir. Ayrıca Adalet Bakanlığı Bedesten resmî mevzuat servisindeki son 45 günlük Resmî Gazete kayıtları her saat taranarak Bakanlık sayfalarındaki yayımlama gecikmesi kapatılır. `TICARET_PRIORITY_SYNC_INTERVAL_SECONDS`, `TICARET_SYNC_INTERVAL_SECONDS`, `TICARET_SOURCES_FILE` ve `TICARET_EXTRA_SOURCES_JSON` değişkenleriyle dağıtım yeniden kod yazmadan özelleştirilebilir.

| Katman | `content_kind` | Kapsam |
|---|---|---|
| Mevzuat | `mevzuat` | Gümrük, ithalat, ihracat, iç ticaret, tüketici, ürün güvenliği, serbest bölgeler, hizmet ticareti, esnaf/kooperatif ve ürün kuralları |
| Devlet destekleri | `destek` | Destek kararları, uygulama esasları, genelgeler, program ve başvuru sayfaları |
| İstatistik ve veri | `veri` | Bakanlık istatistikleri ve resmî veri kaynaklarına açılan bağlantılar |
| Müşavirlik/pazar raporları | `rapor` | Ticaret müşavirleri ve ataşelerden gelen ülke, sektör, pazar, ihale ve ticari bilgi içerikleri |
| Ülke/pazar bilgileri | `ulke_bilgisi` | Yurt dışı teşkilatı ülke sayfaları ve doğrudan yayımlanan ülke belgeleri |
| İletişim | `iletisim` | Müşavirlik/ataşelik listeleri, adres ve iletişim servisleri |
| Bakanlık yayınları | `yayin` | Faaliyet, strateji, performans ve diğer Bakanlık rapor/yayınları |

Yeni araçlar:

* `list_ticaret_sources`: katmanları, resmî başlangıç URL'lerini ve canlı kayıt sayılarını gösterir.
* `search_ticaret_catalog`: katman, kaynak, belge türü, yıl ve mülga durumu filtreleriyle arar.
* `get_ticaret_document`: resmî HTML/PDF/DOCX/XLSX/CSV/ZIP içeriklerini güvenli sınırlar içinde getirir.
* `search_ticaret_content`: seçilen en fazla 25 belgenin tam metninde bağlamlı arama yapar.
* `get_ticaret_catalog_status`: son yenileme, sonraki tarama, kapsam parmak izi ve kaynak hatalarını verir.
* `describe_product_image`: ürün fotoğrafından yalnızca görünür evsafları (malzeme ipuçları, renkler, bileşenler, etiket metni, ambalaj) ve sınıflandırmayı Engelleyen eksik soruları çıkarır. Sonuç GTİP değildir; kullanıcı evsafı onayladıktan sonra `suggest_candidate_tariff_codes` çağrılır.
* `prepare_customs_precheck`: ürün, aday GTİP, menşe ve maliyet girdileri için TAREKS/TSE, ürün güvenliği, kimyasallar, gümrük kıymeti, vergi ve ticaret politikası önlemlerine ilişkin tarihli resmî kanıt paketi hazırlar.
* `sync_official_tariff_data`, `lookup_tariff_measures`, `resolve_turkish_tariff_tree`, `calculate_import_landed_cost`, `compare_tariff_snapshots`: 2026 İthalat Rejimi ve İGV arşivlerini SHA-256 ile sürümler; GTİP/menşe sütununu kaynak dosya, sayfa ve satır düzeyinde gösterir. Karar ağacı HS6 → CN8 → Türkiye 10 → GTİP12 dallarını otomatik seçim yapmadan açar; kısa kodda oran yalnız bütün alt GTİP12 satırlarında ortaksa güvenli oran olarak döner.
* `sync_classification_evidence`, `search_classification_evidence`: DG TAXUD'un geçerli AB sınıflandırma tüzükleri konsolide listesini metin olarak SHA-256 ile sürümler; CN kodu, tüzük referansı, sayfa ve gerekçe parçalarını aranabilir yapar. Bu veri yalnız karşılaştırmalı sınıflandırma kanıtıdır; Türkiye GTİP12 veya Türkiye vergi oranı değildir. EBTI sonuç sayfaları ve açık kullanım hakkı doğrulanmamış başvuru fotoğrafları otomatik taranmaz.
* `sync_import_control_rules`, `lookup_import_controls`, `compare_import_control_snapshots`: güncel Ürün Güvenliği ve Denetimi tebliğlerinin kaynakta belirtilen kapsam eklerini resmî konsolide metin veya resmî ek arşivinden indeksler; liste kapsamını TAREKS risk sonucu ve fiilî denetimden ayırır. 2026/21 için yalnız kapsam oluşturan Ek-1/A–D ile Ek-2 alınır; form ekleri dışarıda bırakılır ve 168 GTİP satırı indekslenir.

Kontrol tebliğlerinin ilk soğuk eşitlemesi, resmî Bedesten hız sınırına saygı göstermek için tek tek ve aralıklı yapılır; birkaç dakika sürebilir. Sonraki sorgular `/data` içindeki snapshot'tan yanıtlanır ve altı saatte bir güncellenir. `CONTROL_REQUEST_INTERVAL_SECONDS` varsayılanı `6.5` saniyedir; resmî servisin sınırını aşacak şekilde düşürülmemelidir.

Mevzuat/Resmî Gazete sunucusu geçerli TLS uç sertifikasıyla birlikte zaman zaman ara sertifikayı göndermediği için uygulama yalnızca DigiCert tarafından yayımlanan **GeoTrust TLS RSA CA G1** ara sertifikasını varsayılan güven zincirine ekler. Kök güveni, alan adı kontrolü, imza ve geçerlilik tarihleri kapatılmaz; `verify=False` kullanılmaz.

## Gümrükçe’ye Sor

Web arayüzündeki **Gümrükçe’ye Sor** sekmesi üç güvenlik aşaması kullanır. Fotoğraf cihazda önizlendikten sonra görünen **Ürünü Analiz Et** düğmesiyle kullanıcı analizi açıkça başlatır; görsel bu eylemden önce sunucuya gönderilmez. Fotoğraf yalnızca ürün evsafına çevrilir; tanım, görünen marka/model, ölçü, etiket metni, görünen ve belirsiz özellikler düzenlenebilir satırlara gelir. Kullanıcı bu alanları açıkça onaylamadan sınıflandırma başlamaz. En fazla beş **aday** kod gösterilir fakat ilk aday otomatik seçilmez. Her aday aktif Türk tarife satırında doğrulanır ve varsa resmî AB sınıflandırma tüzüğü sayfalarıyla desteklenir. Kullanıcı bir aday seçince resmî HS6 → CN8 → Türkiye 10 → GTİP12 ağacı adım adım açılır; TAREKS kapsam sorgusu yalnız doğrulanmış 12 haneli satırda çalışır. Vergi oranları, kısa kod altında bütün GTİP12 satırlarında ortaksa gösterilir; menşe/dipnot bakımından ayrışan oranlar kesin sonuç gibi sunulmaz.

Çalışma masasında ayrıca **Tarife & Maliyet**, **Kontroller & Belgeler**, **Değişiklikler**, **Gümrük Danışmanları** ve **İşlem Rehberi** sekmeleri bulunur. Tarife ekranı resmî workbook/sheet/row ve arşiv checksum'unu; kontrol ekranı tebliğ Ek-1 satırını, yetkili sistemi ve risk uyarısını; değişiklik ekranı snapshot farklarını, cihazdaki GTİP izleme listesini ve kaydedilmiş ön değerlendirmeleri gösterir.

**Gümrük Danışmanları** alanında kullanıcı, oluşturduğu analiz paketini yönetici onaylı bağımsız bir mevzuat danışmanına kontrollü biçimde gönderebilir ve uygulama içinde mesajlaşabilir. Danışman kaydı ücretsizdir; profil değişiklikleri yeniden incelemeye alınır. Ürün görseli, Google e-postası ve mali tutarlar otomatik paylaşılmaz. Bu profiller gümrük müşavirliği yetkisi, gümrükte temsil veya fiilî gümrük işlemi hizmeti anlamına gelmez; bağlayıcı karar gereken durumda BTB ve mevzuatın gerektirdiği yetkili kanallar ayrıca kullanılmalıdır.

Maliyet motoru gümrük vergisi ve İGV dışında ek mali yükümlülük, damping/sübvansiyon, KKDF, KDV, ÖTV ve gözetim kalemlerini de ayrı ayrı ister. Yapılandırılmış canlı kaynağa henüz bağlanmamış bir kalem otomatik olarak `0` kabul edilmez: kullanıcı resmî kaynaktan uygulanmadığını doğruladıysa `0` girmeli, aksi halde toplam maliyet bilinçli olarak eksik bırakılır. Sonuçtaki kapsam matrisi her kalemi `verified_snapshot`, `partial_snapshot`, `not_integrated` veya `user_confirmation_required` olarak açıkça gösterir.

Sınıflandırma kalitesi [customs_classification_v1.jsonl](benchmarks/customs_classification_v1.jsonl) içindeki kaynak URL'si, sayfa, tüzük numarası ve arşiv SHA-256 değeri sabitlenmiş resmî AB karar örnekleriyle ölçülür. Ayrı [tarihsel Türk BTB takımı](benchmarks/turkish_btb_gtip12_historical_v1.jsonl), İstanbul Gümrük ve Ticaret Bölge Müdürlüğünün resmî bülteninde yayımlanan dört gerekçeli 2016 örneğini GTİP12 Top-1/Top-3 ölçümü için kullanır. `customs_benchmark.py` hedef derinliğine göre HS6, CN8 ve GTİP12 metriklerini ayrı hesaplar. Tarihsel takım güncel tarife geçerliliği veya BTB'nin hak sahibi dışındaki kişiler bakımından hukuki bağlayıcılığı iddiasında bulunmaz.

```bash
python customs_benchmark.py predictions.json --cases benchmarks/turkish_btb_gtip12_historical_v1.jsonl
```

* Fotoğraf tek başına kesin veya bağlayıcı GTİP üretmez. Kesin sınıflandırma için teknik belge ve gerektiğinde Bağlayıcı Tarife Bilgisi gerekir.
* Güvenlik sorusu/CAPTCHA kullanan Bakanlık Tarife Arama Motoru otomatik aşılmaz; sonuçlarda yalnızca manuel doğrulama bağlantısı olarak yer alır.
* EBTI, CLASS, CN 2026 ve TARIC karşılaştırmalı sınıflandırma kanıtıdır; bunların kodları Türkiye GTİP12 veya Türkiye vergi oranı olarak doğrudan kullanılmaz.
* EBTI metinleri ve resmî indirme verileri kaynak olarak kullanılabilir. Açık kullanım hakkı teyit edilmemiş EBTI ürün görselleri topluca kopyalanmaz ve model eğitimine alınmaz.
* Her sonuç tarihli resmî kaynak zinciri, belirsizlikler ve zorunlu hukuki uyarıyla birlikte döner. Sistem yüzde yüz doğruluk veya bağlayıcı idari karar iddiasında bulunmaz.

Görsel evsaf çıkarımı ve resmî kanıt paketinin yorumlanması tek bir OpenRouter anahtarıyla çalışır. Görsel analizde modeller sırayla yedeklenir. Tarife sınıflandırmasında ise Gemini ve GLM 5.3 Flash aynı onaylı evsafı birbirinden bağımsız değerlendirir; ilk kodları ayrışırsa Grok/GPT/Claude zincirindeki ilk kullanılabilir farklı model hakem olur. Güven puanı modelin kendi iddiasından değil, bağımsız model uzlaşması, aktif Türk tarife satırı, resmî sınıflandırma gerekçesi ve eksik ayırt edici evsaftan hesaplanır. Varsayılan zincir **Gemini → GLM 5.3 Flash → Grok → GPT → Claude** şeklindedir:

```text
OPENROUTER_API_KEY=<sunucuda gizli değer>
OPENROUTER_VISION_MODELS=~google/gemini-flash-latest,z-ai/glm-5.3-flash,~x-ai/grok-latest,openai/gpt-chat-latest,~anthropic/claude-opus-latest
OPENROUTER_CUSTOMS_MODELS=~google/gemini-flash-latest,z-ai/glm-5.3-flash,~x-ai/grok-latest,openai/gpt-chat-latest,~anthropic/claude-opus-latest
CLASSIFICATION_SYNC_INTERVAL_SECONDS=86400
```

Her çağrı katı JSON şeması ve `require_parameters=true` kullanır; bu nedenle görsel giriş veya yapılandırılmış çıktı desteği olmayan uçlar seçilmez. `data_collection=deny`, istemleri veri saklayabilen sağlayıcı uçlarına göndermemek için zorunludur. Nano Banana bir görsel üretim/düzenleme modelidir ve bu metin çıkarım akışında kullanılmaz. Model ürün adı, kategori, kapsamlı tanım, bileşim, kullanım, görünür menşe ibaresi, marka/model, ölçü, etiket, renk, fiziksel yapı, parçalar, çalışma mekanizması, ambalaj ve sınıflandırma sorularını ayrı alanlara çıkarır. Görselden belirlenemeyen menşe, teknik değer ve maliyet girdilerini uydurmak yerine kullanıcıya tamamlanacak bilgi olarak gösterir.

`OPENROUTER_API_KEY` yoksa arayüz uydurma yanıt üretmez; yalnızca güncel resmî kanıt paketini ve eksik bilgi listesini gösteren `evidence_only` modunda çalışır. Yüklenen JPEG/PNG/WebP görseli yeniden kodlanarak metaverisi temizlenir, kalıcı olarak saklanmaz ve istek başına 8 MB / 25 megapiksel sınırı uygulanır.

> Hukuki yorumlar bilgilendirme amaçlıdır. Sonuçlarda verilen resmî URL, tarih, sayı, mülga/yürürlük durumu ve varsa sonraki değişiklikler karar öncesinde doğrulanmalıdır.

## ChatGPT ve Codex bağlantısı

Uzak MCP adresi: `https://mevzuat-mcp.seymata.com/mcp`

Tanıtım ve fiyatlandırma sayfası: `https://mevzuat-mcp.seymata.com/`

Web araştırma uygulaması: `https://mevzuat-mcp.seymata.com/app`

Arayüzde Ticaret Bakanlığının yedi bilgi katmanı canlı kayıt sayılarıyla ayrı gösterilir; kaynak, belge türü, yıl ve mülga durumu filtrelenebilir. Seçilen kaydın resmî kaynak zinciri, tam metni ve kopyalanabilir atfı aynı ekranda açılır. **Genel mevzuat** görünümü Bedesten resmî servisine bağlı ayrı arama alanıdır.

> Coolify dağıtımı v1.8.0 sağlık, web arayüzü ve MCP araç taramasıyla doğrulanır. Snapshot verilerini kalıcı tutmak için uygulamada `/data` hedefine persistent volume bağlayın; imaj `MEVZUAT_DATA_DIR=/data` ile hazır gelir.

### Google ile giriş ve SEO

Google OAuth istemcisinde **Web application** türü seçilir ve yetkili yönlendirme adresi olarak yalnızca şu tam adres eklenir:

```text
https://mevzuat-mcp.seymata.com/auth/google/callback
```

Coolify ortam değişkenleri:

```text
PUBLIC_BASE_URL=https://mevzuat-mcp.seymata.com
GOOGLE_CLIENT_ID=<Google OAuth web client ID>
GOOGLE_CLIENT_SECRET=<Google OAuth client secret>
AUTH_SESSION_SECRET=<en az 32 karakter kriptografik rastgele değer>
GOOGLE_SITE_VERIFICATION=<Search Console doğrulama kodu, isteğe bağlı>
```

`GOOGLE_CLIENT_SECRET` ve `AUTH_SESSION_SECRET` hiçbir zaman tarayıcıya gönderilmez. OAuth access/refresh tokenları saklanmaz; yalnız doğrulanmış profil alanları ve imzalı birinci taraf oturum çerezi kullanılır. Anahtarlar eklenmediyse Google düğmesi kurulum uyarısı gösterir ve misafir erişimi çalışmaya devam eder.

### Abonelik, kota ve kanıt dosyaları

Google hesabıyla giriş yapan kullanıcılar Başlangıç, Uzman, Ekip ve Kurumsal paketlerini; aylık kullanım sayaçlarını ve sunucuda saklanan kanıt dosyalarını **Hesabım** alanında görür. Görsel kalıcı olarak saklanmaz. Kanıt dosyası analiz sonucunu; kontrol zamanı, GTİP, menşe, yürürlük referansı, resmî URL’ler ve etkin tarife/kontrol snapshot SHA-256 değerleriyle birlikte JSON olarak saklar ve dışa aktarır. Yönetici adresleri virgülle ayrılmış `ADMIN_EMAILS` değişkeninden alınır; `/admin` paket/durum değişikliklerini denetim günlüğüne yazar.

Kart verisini uygulamaya almayan Stripe Billing + hosted Checkout için Coolify’a aşağıdaki Secret değerlerini ekleyin. Stripe Dashboard’da Uzman ve Ekip ürünlerinin aylık/yıllık tekrar eden TRY fiyatlarını oluşturup gerçek `price_` kimliklerini kullanın:

```text
ADMIN_EMAILS=<yönetici Google e-posta adresleri, virgülle ayrılmış>
STRIPE_SECRET_KEY=<sk_test_ veya canlıda sk_live_ ile başlayan gizli anahtar>
STRIPE_WEBHOOK_SECRET=<whsec_ ile başlayan endpoint imza anahtarı>
STRIPE_PRICE_EXPERT_MONTHLY=<price_ kimliği>
STRIPE_PRICE_EXPERT_YEARLY=<price_ kimliği>
STRIPE_PRICE_TEAM_MONTHLY=<price_ kimliği>
STRIPE_PRICE_TEAM_YEARLY=<price_ kimliği>
STRIPE_AUTOMATIC_TAX=false
```

Stripe webhook adresi `https://mevzuat-mcp.seymata.com/api/billing/stripe/webhook` olmalı ve yalnız `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed` olaylarını göndermelidir. Müşteri Portalı, paket değişikliği/iptal ve ödeme yöntemi yönetimini Stripe’ın barındırdığı sayfada yapar. `STRIPE_AUTOMATIC_TAX` yalnız Stripe Tax kayıtları hazırlandıktan sonra `true` yapılmalıdır. Anahtar, webhook secret veya Price ID’lerden biri eksikse ödeme güvenli biçimde kapalı kalır; paket ve fiyat seçimi tarayıcıdan değil sunucudaki katalogdan doğrulanır.

Landing page; canonical, Open Graph/Twitter kartları, `SoftwareApplication` ve `FAQPage` yapılandırılmış verisi, `/robots.txt`, `/sitemap.xml`, manifest ve indekslenmeyen `/app` çalışma alanıyla hazırdır. Google Search Console tarafında alan adı doğrulandıktan sonra `https://mevzuat-mcp.seymata.com/sitemap.xml` gönderilmelidir; indeks kararı ve sıralama Google'a aittir.

ChatGPT'de geliştirici modu açıkken **Ayarlar → Uygulamalar → Oluştur** ekranında bu adresi endpoint olarak verin, kimlik doğrulamayı **Yok** seçin ve **Araçları tara** ile 44 aracı yükleyin. Tarife, maliyet, ithalat kontrolü ve Gümrükçe araçları MCP Apps yapılandırılmış sonuç görünümünü destekler. Codex için:

```bash
codex mcp add mevzuat-mcp --url https://mevzuat-mcp.seymata.com/mcp
```

Responses API örneği:

```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="gpt-5.4",
    input="4458 sayılı Gümrük Kanununa göre bu ithalat işlemini resmî kaynaklarıyla değerlendir.",
    tools=[{
        "type": "mcp",
        "server_label": "turkiye_mevzuat_ticaret",
        "server_url": "https://mevzuat-mcp.seymata.com/mcp",
        "require_approval": "never",
    }],
)
print(response.output_text)
```

---
🌐 **En Kolay Yol: Ücretsiz Remote MCP (Claude Desktop için)**

Hiçbir kurulum gerektirmeyen, doğrudan kullanıma hazır MCP sunucusu:

1. Claude Desktop'ı açın
2. **Settings > Connectors > Add custom connector**
3. Açılan pencerede:
   * **Name:** `Mevzuat MCP`
   * **URL:** `https://mevzuat.surucu.dev/mcp`
4. **Save** butonuna basın

Hepsi bu kadar! Artık Mevzuat MCP ile konuşabilirsiniz.

> **Not:** Bu ücretsiz sunucu topluluk için sağlanmaktadır. Yoğun kullanım için kendi sunucunuzu kurmanız önerilir.

---
🪐 **Google Antigravity ile Kullanım**

1. **Agent session** açın ve editörün yan panelindeki **"…"** dropdown menüsüne tıklayın
2. **MCP Servers** seçeneğini seçin - MCP Store açılacak
3. Üstteki **Manage MCP Servers** butonuna tıklayın
4. **View raw config** seçeneğine tıklayın
5. `mcp_config.json` dosyasına aşağıdaki yapılandırmayı ekleyin:

```json
{
  "mcpServers": {
    "mevzuat-mcp": {
      "serverUrl": "https://mevzuat.surucu.dev/mcp/",
      "headers": {
        "Content-Type": "application/json"
      }
    }
  }
}
```

> 💡 **İpucu:** Remote MCP sayesinde Python, uv veya herhangi bir kurulum yapmadan doğrudan Google Antigravity üzerinden Mevzuat Bilgi Sistemi'ne erişebilirsiniz!

### Lokal `uv` Kurulumu — Kopyala-Yapıştır

> **Ön Gereksinimler:** Bilgisayarınızda **Python**, **`uv`** ([kurulum](https://docs.astral.sh/uv/getting-started/installation/)) ve **Node.js** ([indir](https://nodejs.org/en/download)) kurulu olmalı. (Node.js yalnızca aşağıdaki kurulum komutunu çalıştırmak için gerekir; MCP'yi `uvx` çalıştırır.)

Aşağıdaki **bloğun tamamını** terminale yapıştırın. Komut, Antigravity'nin okuduğu `~/.gemini/config/mcp_config.json` dosyasını sizin yerinize oluşturur/günceller (varsa diğer sunucularınız korunur):

**macOS / Linux** (Terminal):

```bash
node - <<'MEVZUAT'
const fs=require("fs"),os=require("os"),path=require("path");
const dir=path.join(os.homedir(),".gemini","config"),file=path.join(dir,"mcp_config.json");
fs.mkdirSync(dir,{recursive:true});
let cfg={};try{cfg=JSON.parse(fs.readFileSync(file,"utf8"))}catch{}
if(typeof cfg!=="object"||cfg===null||Array.isArray(cfg))cfg={};
if(typeof cfg.mcpServers!=="object"||cfg.mcpServers===null)cfg.mcpServers={};
cfg.mcpServers["mevzuat-mcp"]={command:"uvx",args:["--from","git+https://github.com/saidsurucu/mevzuat-mcp","mevzuat-mcp"]};
fs.writeFileSync(file,JSON.stringify(cfg,null,2)+"\n");
console.log("mevzuat-mcp eklendi -> "+file);
MEVZUAT
```

**Windows** (PowerShell):

```powershell
@'
const fs=require("fs"),os=require("os"),path=require("path");
const dir=path.join(os.homedir(),".gemini","config"),file=path.join(dir,"mcp_config.json");
fs.mkdirSync(dir,{recursive:true});
let cfg={};try{cfg=JSON.parse(fs.readFileSync(file,"utf8"))}catch{}
if(typeof cfg!=="object"||cfg===null||Array.isArray(cfg))cfg={};
if(typeof cfg.mcpServers!=="object"||cfg.mcpServers===null)cfg.mcpServers={};
cfg.mcpServers["mevzuat-mcp"]={command:"uvx",args:["--from","git+https://github.com/saidsurucu/mevzuat-mcp","mevzuat-mcp"]};
fs.writeFileSync(file,JSON.stringify(cfg,null,2)+"\n");
console.log("mevzuat-mcp eklendi -> "+file);
'@ | node -
```

Komut `mevzuat-mcp eklendi -> ...` çıktısını verdiğinde kurulum tamamlanmıştır. Antigravity'yi (açıksa kapatıp) yeniden başlatın; `mevzuat-mcp` araçları otomatik yüklenir.

> 💡 **İpucu:** Lokal kurulumda mevzuat kaynaklarına erişim doğrudan bilgisayarınızda `uvx` ile çalışır; uzaktan sunucuya ihtiyaç duymaz.

---
🚀 **Claude Haricindeki Modellerle Kullanmak İçin Çok Kolay Kurulum (Örnek: 5ire için)**

Bu bölüm, Mevzuat MCP aracını 5ire gibi Claude Desktop dışındaki MCP istemcileriyle kullanmak isteyenler içindir.

* **Python Kurulumu:** Sisteminizde Python 3.11 veya üzeri kurulu olmalıdır. Kurulum sırasında "**Add Python to PATH**" (Python'ı PATH'e ekle) seçeneğini işaretlemeyi unutmayın. [Buradan](https://www.python.org/downloads/) indirebilirsiniz.
* **Git Kurulumu (Windows):** Bilgisayarınıza [git](https://git-scm.com/downloads/win) yazılımını indirip kurun. "Git for Windows/x64 Setup" seçeneğini indirmelisiniz.
* **`uv` Kurulumu:**
    * **Windows Kullanıcıları (PowerShell):** Bir CMD ekranı açın ve bu kodu çalıştırın: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
    * **Mac/Linux Kullanıcıları (Terminal):** Bir Terminal ekranı açın ve bu kodu çalıştırın: `curl -LsSf https://astral.sh/uv/install.sh | sh`
* **Microsoft Visual C++ Redistributable (Windows):** Bazı Python paketlerinin doğru çalışması için gereklidir. [Buradan](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170) indirip kurun.
* İşletim sisteminize uygun [5ire](https://5ire.app) MCP istemcisini indirip kurun.
* 5ire'ı açın. **Workspace -> Providers** menüsünden kullanmak istediğiniz LLM servisinin API anahtarını girin.
* **Tools** menüsüne girin. **+Local** veya **New** yazan butona basın.
    * **Tool Key:** `mevzuatmcp`
    * **Name:** `Mevzuat MCP`
    * **Command:**
        ```
        uvx --from git+https://github.com/saidsurucu/mevzuat-mcp mevzuat-mcp
        ```
    * **Save** butonuna basarak kaydedin.
![5ire ayarları](./5ire-settings.png)
* Şimdi **Tools** altında **Mevzuat MCP**'yi görüyor olmalısınız. Üstüne geldiğinizde sağda çıkan butona tıklayıp etkinleştirin (yeşil ışık yanmalı).
* Artık Mevzuat MCP ile konuşabilirsiniz.

---
⚙️ **Claude Desktop Manuel Kurulumu**


1.  **Ön Gereksinimler:** Python, `uv`, (Windows için) Microsoft Visual C++ Redistributable'ın sisteminizde kurulu olduğundan emin olun. Detaylı bilgi için yukarıdaki "5ire için Kurulum" bölümündeki ilgili adımlara bakabilirsiniz.
2.  Claude Desktop **Settings -> Developer -> Edit Config**.
3.  Açılan `claude_desktop_config.json` dosyasına `mcpServers` altına ekleyin:

    ```json
    {
      "mcpServers": {
        // ... (varsa diğer sunucularınız) ...
        "Mevzuat MCP": {
          "command": "uvx",
          "args": [
            "--from",
            "git+https://github.com/saidsurucu/mevzuat-mcp",
            "mevzuat-mcp"
          ]
        }
      }
    }
    ```
4.  Claude Desktop'ı kapatıp yeniden başlatın.

---
🔑 **API Anahtarları (Opsiyonel)**

### Semantik Arama - OpenRouter API

Tüm `search_within_*` araçlarında `semantic=True` ile doğal dilde arama yapabilmek için:

1. [OpenRouter](https://openrouter.ai/) üzerinden API anahtarı alın
2. Environment variable olarak ayarlayın:
   ```bash
   OPENROUTER_API_KEY=your_api_key_here
   ```
3. Varsayılan model: `google/gemini-embedding-001` (3072 boyut). Alternatif olarak:
   ```bash
   EMBEDDING_MODEL=intfloat/multilingual-e5-large  # 1024 boyut
   ```
4. API anahtarı olmadan da tüm araçlar çalışır, sadece `semantic=True` kullanılamaz

### Mistral OCR

CB Kararı ve CB Genelgesi gibi PDF tabanlı mevzuatlar için Mistral OCR kullanılır:

1. [Mistral AI Console](https://console.mistral.ai/) üzerinden API anahtarı alın
2. Environment variable olarak ayarlayın:
   ```bash
   MISTRAL_API_KEY=your_api_key_here
   ```
3. API anahtarı olmadan da sistem çalışır, ancak PDF'ler markitdown ile işlenir (daha düşük kalite)

---
🛠️ **Kullanılabilir Araçlar (MCP Tools)**

Bu FastMCP sunucusu LLM modelleri için **43 araç** sunar (üç resmî kaynak ailesi).

### A. mevzuat.gov.tr Araçları (21 araç)

Türe özel arama ve içerik araçları. Her mevzuat türü için ayrı tool'lar.

#### Kanun (Laws)
* **`search_kanun`**: Kanun başlık ve içeriklerinde arama yapar
* **`search_within_kanun`**: Kanun maddelerinde anahtar kelime veya semantik arama yapar

#### KHK (Decree Laws)
* **`search_khk`**: KHK başlık ve içeriklerinde arama yapar
* **`search_within_khk`**: KHK maddelerinde anahtar kelime veya semantik arama yapar

#### Tüzük (Statutes)
* **`search_tuzuk`**: Tüzük başlık ve içeriklerinde arama yapar
* **`search_within_tuzuk`**: Tüzük maddelerinde anahtar kelime veya semantik arama yapar

#### Kurum Yönetmeliği (Institutional Regulations)
* **`search_kurum_yonetmelik`**: Kurum yönetmeliği başlık ve içeriklerinde arama yapar
* **`search_within_kurum_yonetmelik`**: Kurum yönetmeliği maddelerinde anahtar kelime veya semantik arama yapar

#### Cumhurbaşkanlığı Kararnamesi (Presidential Decrees)
* **`search_cbk`**: CB Kararnamesi başlık ve içeriklerinde arama yapar
* **`search_within_cbk`**: CB Kararnamesi maddelerinde anahtar kelime veya semantik arama yapar

#### Cumhurbaşkanı Kararı (Presidential Decisions)
* **`search_cbbaskankarar`**: CB Kararı başlık ve içeriklerinde arama yapar
* **`get_cbbaskankarar_content`**: CB Kararı tam içeriğini getirir (PDF - OCR destekli)
* **`search_within_cbbaskankarar`**: CB Kararı içeriğinde anahtar kelime veya semantik arama yapar

#### CB Yönetmeliği (Presidential Regulations)
* **`search_cbyonetmelik`**: CB Yönetmeliği başlık ve içeriklerinde arama yapar
* **`search_within_cbyonetmelik`**: CB Yönetmeliği maddelerinde anahtar kelime veya semantik arama yapar

#### CB Genelgesi (Presidential Circulars)
* **`search_cbgenelge`**: CB Genelgesi başlıklarında arama yapar
* **`get_cbgenelge_content`**: CB Genelgesi tam içeriğini getirir (PDF - OCR destekli)
* **`search_within_cbgenelge`**: CB Genelgesi içeriğinde anahtar kelime veya semantik arama yapar

#### Tebliğ (Communiqués)
* **`search_teblig`**: Tebliğ başlık ve içeriklerinde arama yapar
* **`get_teblig_content`**: Tebliğ tam içeriğini getirir
* **`search_within_teblig`**: Tebliğ maddelerinde anahtar kelime veya semantik arama yapar

#### mevzuat.gov.tr Ortak Parametreler

**Arama Tool'ları için:**
* `aranacak_ifade`: Aranacak kelime veya kelime grupları (AND, OR, NOT operatörleri desteklenir)
* `tam_cumle`: Tam cümle eşleşmesi (exact phrase)
* `baslangic_tarihi` / `bitis_tarihi`: Tarih aralığı filtreleme
* `page_number`, `page_size`: Sayfalama

**İçinde Arama Tool'ları için:**
* `mevzuat_no`: Mevzuat numarası (arama sonucundan alınır)
* `keyword`: Aranacak anahtar kelime veya doğal dilde sorgu
* `semantic`: `True` ise semantik arama, `False` ise anahtar kelime araması (varsayılan: `False`)
* `case_sensitive`: Büyük/küçük harf duyarlılığı (sadece keyword modunda)
* `max_results`: Maksimum sonuç sayısı

### B. bedesten.adalet.gov.tr Araçları (5 araç)

Tüm mevzuat türlerini tek araçla kapsayan birleşik araçlar. Gerekçe ve içindekiler gibi ek özellikler sunar.

#### **`search_mevzuat`** - Birleşik Mevzuat Arama
Tüm 12 mevzuat türünde başlık ve içerik araması yapar.
* `phrase`: İçerikte tam metin arama (Solr sözdizimi)
* `mevzuat_adi`: Mevzuat adı/başlığında arama
* `mevzuat_no`: Mevzuat numarası filtresi
* `mevzuat_tur`: Mevzuat türü filtresi (KANUN, KHK, TUZUK, YONETMELIK, CB_KARARNAME, CB_KARAR, CB_YONETMELIK, CB_GENELGE, KKY, UY, TEBLIGLER, MULGA)
* `basliktaAra`: Sadece başlıkta ara (varsayılan: true)
* `tamCumle`: Tam cümle eşleşmesi (varsayılan: false)
* `resmi_gazete_tarihi`: Resmi Gazete tarihi filtresi (GG/AA/YYYY)
* `resmi_gazete_sayisi`: Resmi Gazete sayısı filtresi
* `page`, `page_size`: Sayfalama

#### **`get_mevzuat_content`** - Tam Metin Getirme
Bir mevzuatın tam metnini Markdown formatında getirir.
* `mevzuat_id`: Mevzuat ID'si (`search_mevzuat` sonucundan alınır, mevzuat numarası değildir)

#### **`search_within_mevzuat`** - Madde Bazında Arama
Bir mevzuatın maddeleri içinde anahtar kelime araması yapar.
* `mevzuat_id`: Mevzuat ID'si (`search_mevzuat` sonucundan alınır)
* `keyword`: Aranacak kelime veya Boolean ifade (AND, OR, NOT)
* `case_sensitive`: Büyük/küçük harf duyarlılığı (varsayılan: false)
* `max_results`: Maksimum sonuç sayısı (varsayılan: 25)

#### **`get_mevzuat_gerekce`** - Kanun Gerekçesi
Bir kanunun gerekçesini getirir (amaç, komisyon raporları, madde gerekçeleri).
* `gerekce_id`: Gerekçe ID'si (`search_mevzuat` sonucundan alınır)

#### **`get_mevzuat_madde_tree`** - İçindekiler / Madde Ağacı
Bir mevzuatın bölüm-madde hiyerarşisini getirir.
* `mevzuat_id`: Mevzuat ID'si (`search_mevzuat` sonucundan alınır)

### Arama Modları

**Keyword Modu** (`semantic=False`, varsayılan):
```
keyword: "yatırımcı AND tazmin"
```
Boolean operatörler (AND, OR, NOT) ile kesin kelime eşleşmesi. Operatörler BÜYÜK HARF olmalıdır.

**Semantik Mod** (`semantic=True`, sadece mevzuat.gov.tr araçları):
```
keyword: "yatırımcının zararının tazmini"
```
Doğal dilde anlam tabanlı arama. Kelime eşleşmesi aramaz, kavramsal benzerlik ile sonuç döner. `OPENROUTER_API_KEY` gerektirir.

---
📜 **Lisans**

Bu proje MIT Lisansı altında lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakınız.
