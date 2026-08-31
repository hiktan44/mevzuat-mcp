# Agentic Security Firewall

Bu belge, Gümrükçe ve MCP ajan akışlarında uygulanan güvenlik sınırlarını ve yalnızca altyapı yöneticisinin tamamlayabileceği kontrolleri ayırır.

## Uygulamada etkin kontroller

| Katman | Durum | Kontrol |
|---|---|---|
| 1 — Girdi/çıktı | Etkin | Yüksek güvenli prompt injection engeli, haricî kaynak talimat karantinası, LLM öncesi TCKN/kart/anahtar/e-posta/telefon redaksiyonu, kullanıcı nesneleri için fail-closed sahiplik yardımcısı |
| 2 — Çalışma ve ağ | Etkin | Root olmayan `appuser`, görsel yeniden kodlama, HTTPS + alan adı allowlist, özel ağ/localhost/cloud metadata SSRF engeli |
| 3 — Kimlik | Hazır, isteğe bağlı zorunlu | HMAC-SHA256 ajan belirteci; `aud`, `sub`, `iat`, `exp`, en fazla 5 dakika tazelik; tarayıcı Origin denetimi |
| 4 — Tedarik zinciri | Etkin | Kilitli bağımlılık kurulumu, test ve sözdizimi kontrolü, Gitleaks, root olmayan container doğrulaması, Trivy imaj taraması |

## Coolify ortam değişkenleri

Zorunlu ajan kimliği istenirse Coolify uygulamasına aşağıdakiler eklenir:

```text
AGENT_GATEWAY_SECRET=<en az 32 bayt rastgele sır>
REQUIRE_AGENT_IDENTITY=1
```

Bu seçenek etkinleştirildiğinde AI uçları geçerli Google oturumu veya `Authorization: Bearer <kısa-ömürlü-agent-token>` ister. Önce istemcilerin bu kimlik akışına geçirildiği doğrulanmalıdır.

## Sunucu yöneticisi tarafından tamamlanacak katmanlar

- Coolify/Docker host üzerinde gVisor (`runsc`) veya eşdeğer izole runtime seçimi.
- Container çıkış trafiğinin yalnız resmî kaynak alan adları ve `openrouter.ai` için açılması; `169.254.169.254`, özel ağlar ve yerel servislerin ağ seviyesinde engellenmesi.
- Dosya sisteminin salt okunur çalıştırılması; yalnız `/data` için yazılabilir volume bırakılması.
- Registry üzerinden dağıtıma geçildiğinde imajların Cosign/Sigstore ile imzalanması ve doğrulanmamış imajın çalıştırılmaması.

Bu altyapı kontrolleri uygulama kodundan etkinleştirilemez; Coolify sunucusunda yönetici yetkisi gerekir. Uygulama katmanı aynı hedefleri ayrıca fail-closed URL denetimiyle savunur.
