const demoProducts = {
  textile: {
    file: "TEKSTİL-01",
    product: "Çocuk örme üst giyim",
    code: "6110.20",
    confidence: "%78",
    control: "Ürün güvenliği",
    rule: "2026/14",
    cost: "MENŞE GEREKLİ",
    summary: "Elyaf kompozisyonu ve kullanıcı yaş grubu doğrulanmadan tarife kesinleştirilemez.",
  },
  electronics: {
    file: "ELEKTRONİK-02",
    product: "Kablosuz şarj cihazı",
    code: "8504.40",
    confidence: "%83",
    control: "CE / TAREKS",
    rule: "2026/9",
    cost: "TEKNİK EVSAF",
    summary: "Güç değeri, bağlantı yapısı ve beraber sunulan adaptör kapsamı kontrolü değiştirir.",
  },
  toy: {
    file: "OYUNCAK-03",
    product: "Pilli çocuk oyuncağı",
    code: "9503.00",
    confidence: "%86",
    control: "Oyuncak güvenliği",
    rule: "2026/10",
    cost: "YAŞ GRUBU GEREKLİ",
    summary: "Yaş grubu, pil/elektronik aksam ve malzeme bilgisi fiilî kontrol dosyası için doğrulanmalıdır.",
  },
};

const numberFormat = new Intl.NumberFormat("tr-TR");

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

document.querySelectorAll("[data-demo]").forEach((button) => {
  button.addEventListener("click", () => {
    const demo = demoProducts[button.dataset.demo];
    if (!demo) return;
    document.querySelectorAll("[data-demo]").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-selected", String(selected));
    });
    setText("demoFile", demo.file);
    setText("demoProduct", demo.product);
    setText("demoCode", demo.code);
    setText("demoConfidence", demo.confidence);
    setText("demoControl", demo.control);
    setText("demoRule", demo.rule);
    setText("demoCost", demo.cost);
    setText("demoSummary", demo.summary);
    const card = document.querySelector(".product-file");
    card?.animate(
      [{ opacity: .35, transform: "translate(-50%,-48%)" }, { opacity: 1, transform: "translate(-50%,-50%)" }],
      { duration: 260, easing: "ease-out" },
    );
  });
});

document.querySelectorAll("[data-billing]").forEach((button) => {
  button.addEventListener("click", () => {
    const annual = button.dataset.billing === "annual";
    document.querySelectorAll("[data-billing]").forEach((item) => item.classList.toggle("active", item === button));
    document.querySelectorAll(".price b[data-monthly]").forEach((price) => {
      price.textContent = annual ? price.dataset.annual : price.dataset.monthly;
    });
    document.querySelectorAll("[data-period]").forEach((period) => {
      period.textContent = annual ? "/ yıl + KDV" : "/ ay + KDV";
    });
  });
});

async function loadLiveCoverage() {
  try {
    const response = await fetch("/api/ticaret/status", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const status = await response.json();
    setText("statSources", numberFormat.format(status.source_count || 0));
    setText("statDocuments", numberFormat.format(status.document_count || 0));
    setText("statGazette", status.latest_official_gazette_date || "—");
  } catch (_) {
    // The static copy remains truthful when the live status is temporarily unavailable.
  }
}

async function loadAuthState() {
  const notice = document.getElementById("authNotice");
  const login = document.getElementById("googleLogin");
  const headerLogin = document.getElementById("headerLogin");
  const query = new URLSearchParams(window.location.search);
  try {
    const response = await fetch("/api/auth/me", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("auth unavailable");
    const auth = await response.json();
    if (auth.authenticated && auth.user) {
      const firstName = String(auth.user.name || auth.user.email || "Hesabım").split(" ")[0];
      if (login) {
        login.querySelector("span").textContent = `${firstName} olarak uygulamayı aç`;
        login.href = "/app";
      }
      if (headerLogin) {
        headerLogin.textContent = firstName;
        headerLogin.href = "/app";
      }
      if (notice) notice.textContent = `${auth.user.email} hesabıyla giriş yapıldı.`;
      return;
    }
    if (!auth.google_enabled || query.get("auth") === "google-setup") {
      if (notice) {
        notice.classList.add("warning");
        notice.textContent = "Google girişi hazır; yönetici anahtarları eklendiğinde etkinleşecek. Uygulamayı şimdilik misafir olarak açabilirsiniz.";
      }
    } else if (query.get("auth") === "failed") {
      if (notice) {
        notice.classList.add("warning");
        notice.textContent = "Google girişi doğrulanamadı. Lütfen yeniden deneyin.";
      }
    } else if (query.get("auth") === "cancelled" && notice) {
      notice.textContent = "Google giriş işlemi iptal edildi; misafir erişimi açık.";
    }
  } catch (_) {
    if (notice) notice.textContent = "Hesap durumu şu anda alınamadı; misafir erişimini kullanabilirsiniz.";
  }
}

loadLiveCoverage();
loadAuthState();
