# Google OAuth ve arama görünürlüğü kurulum notu

## Google OAuth

1. Google Cloud Console'da bir OAuth 2.0 istemcisi oluşturun; türü `Web application` olmalıdır.
2. Yetkili JavaScript kaynağına `https://gumruksor.com` ekleyin.
3. Yetkili yönlendirme URI'sine tam olarak `https://gumruksor.com/auth/google/callback` ekleyin.
4. Coolify'a `GOOGLE_CLIENT_ID` ve `GOOGLE_CLIENT_SECRET` değerlerini Secret olarak ekleyin.
5. `AUTH_SESSION_SECRET` için en az 32 karakterlik kriptografik rastgele bir değer kullanın; mevcut oturumları düşürmemek için sonradan sebepsiz değiştirmeyin.

Uygulama OAuth erişim veya yenileme tokenlarını saklamaz. Google kimlik tokenı; hedef istemci, sağlayıcı, süre, e-posta doğrulaması ve nonce bakımından sunucuda kontrol edilir. Kullanıcı veritabanında yalnız Google subject, e-posta, ad, profil resmi ve giriş zamanları tutulur.

## Google Search Console

1. Search Console'da `gumruksor.com` mülkünü doğrulayın.
2. HTML meta yöntemi kullanılıyorsa yalnız doğrulama değerini Coolify'da `GOOGLE_SITE_VERIFICATION` değişkenine ekleyin.
3. `https://gumruksor.com/sitemap.xml` adresini gönderin.
4. URL İnceleme aracında ana sayfa için canlı testi çalıştırıp dizine ekleme isteyin.
5. Google'ın zengin sonuç testinde ana sayfadaki `SoftwareApplication` ve `FAQPage` verisini doğrulayın.

Teknik hazırlık indekslenmeyi garanti etmez. Kalıcı organik görünürlük için resmî kaynaklı, özgün ve düzenli güncellenen GTİP/TAREKS açıklama sayfaları ayrıca yayınlanmalıdır; yalnız JavaScript uygulama ekranları SEO içeriği olarak kullanılmamalıdır.
