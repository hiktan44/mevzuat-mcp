# gumruksor.com alan adını Cloudflare ve Coolify üzerinden canlıya alma

Bu not, uygulamayı `https://gumruksor.com` adresinde yayına almak için panel üzerinden yapılacak
adımları sırasıyla anlatır. Kod tarafında yapılması gereken değişiklikler tamamlanmıştır; aşağıdaki
adımlar yalnız Cloudflare ve Coolify arayüzlerinde yapılır.

Sıralama önemlidir: **önce DNS, sonra Coolify alan adı, sonra ortam değişkenleri, en son deploy.**

## 0. Önce sunucunun IP adresini öğrenin

Coolify panelinde **Servers → (sunucunuz)** ekranındaki genel IP adresini not edin. Bu, mevcut
`mevzuat-mcp.seymata.com` adresinin gösterdiği sunucunun IP'siyle aynı olmalıdır.

## 1. Cloudflare'de DNS kaydı

Cloudflare panelinde `gumruksor.com` alan adını açın, **DNS → Records** bölümüne gidin ve iki kayıt
ekleyin:

| Type | Name | Content | Proxy status | TTL |
|------|------|---------|--------------|-----|
| A | `@` | sunucu IP adresi | **DNS only (gri bulut)** | Auto |
| A | `www` | sunucu IP adresi | **DNS only (gri bulut)** | Auto |

Proxy başlangıçta **kapalı (gri bulut)** olmalıdır. Coolify, Let's Encrypt sertifikasını alırken
alan adının doğrudan sunucuya çözümlenmesine ihtiyaç duyar; turuncu bulut açıkken bu doğrulama
başarısız olabilir. Proxy'yi 3. adımdaki sertifika alındıktan sonra açacaksınız.

Alan adı Cloudflare'den yeni alındıysa **Overview** ekranında alan adının `Active` durumda
olduğunu doğrulayın. `Pending Nameserver Update` yazıyorsa DNS kayıtları henüz yayına girmez.

## 2. Coolify'de alan adını uygulamaya tanıtın

1. Coolify panelinde mevcut uygulamayı açın (şu anda `mevzuat-mcp.seymata.com` adresini kullanan
   uygulama).
2. **Configuration → General → Domains** alanına gidin.
3. Mevcut adresi silmeyin. Yeni adresi virgülle ayırarak ekleyin:

   ```text
   https://gumruksor.com,https://mevzuat-mcp.seymata.com
   ```

   İki adresi bir süre birlikte tutmak, eski bağlantıların ve MCP istemci kayıtlarının aniden
   kırılmasını önler. Geçiş tamamlandığında eski adresi buradan kaldırabilirsiniz.
4. **Save** deyin. Henüz deploy etmeyin; önce ortam değişkenlerini güncelleyeceksiniz.

`www.gumruksor.com` adresinin de çalışmasını istiyorsanız onu da listeye ekleyin. Arama motorları
açısından tek bir birincil adres olması gerektiği için `www` sürümünü Cloudflare'de **Rules →
Redirect Rules** ile `gumruksor.com` adresine 301 yönlendirmesi yapmanız önerilir.

## 3. Coolify ortam değişkenleri

Aynı uygulamada **Configuration → Environment Variables** bölümünde şu değerleri ayarlayın:

```text
PUBLIC_BASE_URL=https://gumruksor.com
ADDITIONAL_ALLOWED_ORIGINS=https://www.gumruksor.com,https://mevzuat-mcp.seymata.com
```

`PUBLIC_BASE_URL` uygulamanın kendini tanıttığı tek adrestir. Canonical etiketleri, `sitemap.xml`,
`robots.txt`, Google OAuth dönüş adresi, Stripe dönüş adresleri ve e-posta bağlantıları bu
değerden üretilir.

`ADDITIONAL_ALLOWED_ORIGINS` yalnız geçiş dönemi içindir. Tarayıcıdan gelen POST istekleri
normalde sadece `PUBLIC_BASE_URL` kaynağından kabul edilir; bu değişken eski adresten gelen
isteklerin de kabul edilmesini sağlar. **Eski adres kapatıldığında bu değişkeni boşaltın** —
gereksiz yere açık bırakılan her ek adres, siteler arası istek yüzeyini genişletir.

## 4. Deploy edin

Coolify'de **Deploy** düğmesine basın. Dağıtım bittikten sonra:

1. **Configuration → General** ekranında `gumruksor.com` için sertifikanın alındığını doğrulayın.
2. Tarayıcıda `https://gumruksor.com/health` adresini açın; sağlık yanıtı dönmelidir.
3. `https://gumruksor.com/` açılış sayfasını ve `https://gumruksor.com/app` uygulamasını kontrol edin.

Sertifika alınmadıysa DNS kaydının gerçekten sunucuya çözümlendiğini doğrulayın ve Cloudflare
proxy'sinin hâlâ gri bulut olduğundan emin olun.

## 5. Cloudflare proxy'yi açın (isteğe bağlı)

Sertifika alındıktan sonra Cloudflare korumasını devreye almak isterseniz:

1. **SSL/TLS → Overview** bölümünde şifreleme modunu **Full (strict)** yapın. `Flexible` modu
   yönlendirme döngüsüne yol açar, kullanmayın.
2. **DNS → Records** bölümünde `@` ve `www` kayıtlarının proxy durumunu turuncu buluta çevirin.
3. Proxy açıldıktan sonra MCP akışını (`https://gumruksor.com/mcp`) mutlaka tekrar test edin.
   Cloudflare'in ara belleğe alma davranışı akış tabanlı yanıtları etkileyebilir; sorun görürseniz
   `/mcp` yolu için **Rules → Configuration Rules** ile önbelleği kapatın.

## 6. Alan adına bağlı dış servisleri güncelleyin

Bu adımlar atlanırsa giriş ve ödeme akışları yeni adreste çalışmaz.

**Google OAuth** — Google Cloud Console'da OAuth istemcisini açıp ekleyin:

```text
Yetkili JavaScript kaynağı:   https://gumruksor.com
Yetkili yönlendirme URI'si:   https://gumruksor.com/auth/google/callback
```

Eski adresin girişleri bozulmasın diye `mevzuat-mcp.seymata.com` kayıtlarını hemen silmeyin;
geçiş tamamlandığında kaldırın.

**Stripe** — Dashboard'da webhook adresini güncelleyin:

```text
https://gumruksor.com/api/billing/stripe/webhook
```

Gönderilecek olaylar değişmez: `checkout.session.completed`, `customer.subscription.updated`,
`customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`. Yeni endpoint farklı bir
imza anahtarı üretir; Coolify'daki `STRIPE_WEBHOOK_SECRET` değerini yeni `whsec_` değeriyle
güncelleyin.

**Google Search Console** — `gumruksor.com` mülkünü doğrulayın ve
`https://gumruksor.com/sitemap.xml` adresini gönderin. Eski adres bir süre daha yayındaysa
Search Console'da adres değişikliği aracını kullanmak yerine, eski adresten yenisine 301
yönlendirmesi kurulmasını bekleyin.

**MCP istemcileri** — ChatGPT ve Codex kayıtlarındaki adresi güncelleyin:

```bash
codex mcp add mevzuat-mcp --url https://gumruksor.com/mcp
```

## 7. Geçiş tamamlandığında

Eski adresi kapatmaya karar verdiğinizde sırasıyla:

1. Cloudflare'de `mevzuat-mcp.seymata.com` için `gumruksor.com` adresine 301 yönlendirmesi kurun.
2. Coolify'de uygulamanın Domains alanından eski adresi kaldırın.
3. `ADDITIONAL_ALLOWED_ORIGINS` değişkenini boşaltın ve yeniden deploy edin.
4. Google OAuth istemcisinden eski adres kayıtlarını silin.

## Doğrulama kontrol listesi

- [ ] `https://gumruksor.com/health` yanıt veriyor
- [ ] `https://gumruksor.com/` açılış sayfası açılıyor
- [ ] `https://gumruksor.com/app` uygulaması açılıyor
- [ ] `https://gumruksor.com/robots.txt` içindeki sitemap satırı `gumruksor.com` gösteriyor
- [ ] `https://gumruksor.com/sitemap.xml` adresleri `gumruksor.com` ile başlıyor
- [ ] Google ile giriş yeni adreste çalışıyor
- [ ] `https://gumruksor.com/mcp` üzerinden MCP araç taraması sonuç veriyor
- [ ] Stripe webhook'u yeni adrese test olayı gönderdiğinde 200 dönüyor
