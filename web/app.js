const state = {
  scope: "ticaret",
  activeKind: "",
  offset: 0,
  page: 1,
  limit: 20,
  total: 0,
  currentDocument: null,
  currentContent: "",
  currentOffset: 0,
  currentTrigger: null,
  sourceData: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const form = $("#searchForm");
const queryInput = $("#query");
const resultList = $("#resultList");
const statusNote = $("#status");
const resultCount = $("#resultCount");
const resultsTitle = $("#resultsTitle");
const pagination = $("#pagination");
const prevPage = $("#prevPage");
const nextPage = $("#nextPage");
const pageLabel = $("#pageLabel");
const reader = $("#reader");
const readerContent = $("#readerContent");
const readerSearch = $("#readerSearch");
const loadMoreContent = $("#loadMoreContent");
const numberFormat = new Intl.NumberFormat("tr-TR");

const kindLabels = {
  mevzuat: "Mevzuat",
  destek: "Devlet desteği",
  veri: "Veri ve istatistik",
  rapor: "Rapor",
  ulke_bilgisi: "Ülke bilgisi",
  iletisim: "İletişim",
  yayin: "Yayın",
};

const sourceLabels = {
  gumruk: "Gümrük işlemleri",
  ihracat: "İhracat",
  ithalat: "İthalat",
  destekler: "Devlet destekleri",
  ic_ticaret: "İç ticaret",
  tuketici: "Tüketici",
  serbest_bolgeler: "Serbest bölgeler",
  urun_guvenligi: "Ürün güvenliği",
  hizmet_ticareti: "Hizmet ticareti",
  esnaf_kooperatif: "Esnaf ve kooperatif",
  urun_kurallari: "Ürün kuralları",
  istatistikler_veri: "İstatistikler",
  musavirlik_pazar: "Müşavirlik ve pazar bilgileri",
  musavirlik_blog_guncel: "Güncel müşavirlik raporları",
  yurtdisi_teskilati: "Yurt dışı teşkilatı",
  musavirlik_iletisim: "Müşavirlik iletişim",
  bakanlik_yayinlari: "Bakanlık yayınları",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch (_) {
    return "#";
  }
}

function formatDate(value, includeTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return String(value);
  return new Intl.DateTimeFormat("tr-TR", includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" }).format(date);
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2200);
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage);
  } catch (_) {
    showToast("Kopyalama izni alınamadı.");
  }
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "İstek tamamlanamadı.");
  return data;
}

function setLoading() {
  statusNote.hidden = true;
  pagination.hidden = true;
  resultList.innerHTML = Array.from({ length: 6 }, () => '<div class="skeleton" aria-hidden="true"></div>').join("");
  resultCount.textContent = "…";
  $("#resultContext").textContent = "kaynak taranıyor";
}

function setStatus(title, message, isError = false) {
  resultList.innerHTML = "";
  pagination.hidden = true;
  statusNote.hidden = false;
  statusNote.classList.toggle("error", isError);
  statusNote.querySelector("span").textContent = isError ? "!" : "00";
  statusNote.querySelector("strong").textContent = title;
  statusNote.querySelector("p").textContent = message;
}

function fileCode(documentData) {
  if (documentData.is_repealed) return "MÜL";
  const file = String(documentData.file_type || "").toUpperCase();
  if (file && file !== "LINK") return file.slice(0, 4);
  return (documentData.document_type || kindLabels[documentData.content_kind] || "WEB").slice(0, 4).toUpperCase();
}

function updatePagination(total, current, hasNext) {
  const page = state.scope === "ticaret" ? Math.floor(current / state.limit) + 1 : current;
  const pages = Math.max(1, Math.ceil(total / state.limit));
  pageLabel.textContent = `${page} / ${pages}`;
  prevPage.disabled = page <= 1;
  nextPage.disabled = !hasNext;
  pagination.hidden = total <= state.limit;
}

function renderTicaretResults(data) {
  statusNote.hidden = true;
  resultList.innerHTML = "";
  state.total = data.total;
  resultCount.textContent = numberFormat.format(data.total);
  $("#resultContext").textContent = data.excluded_repealed
    ? `kayıt · ${numberFormat.format(data.excluded_repealed)} mülga hariç`
    : "kayıt";
  updatePagination(data.total, data.offset, data.has_next);

  if (!data.documents.length) {
    setStatus("Bu dosyada kayıt bulunamadı.", "Daha kısa bir ifade deneyin veya kaynak ve yıl filtrelerini kaldırın.");
    resultCount.textContent = "0";
    return;
  }

  data.documents.forEach((doc) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `result-item${doc.is_repealed ? " repealed" : ""}`;
    const meta = [
      sourceLabels[doc.source_id] || doc.source_id,
      doc.document_type || kindLabels[doc.content_kind],
      doc.publication_date || doc.page_updated_at,
      doc.number ? `No ${doc.number}` : "",
    ].filter(Boolean);
    item.innerHTML = `
      <span class="result-node">${escapeHtml(fileCode(doc))}</span>
      <span>
        <strong class="result-title">${escapeHtml(doc.title)}</strong>
        ${doc.context ? `<span class="result-context">${escapeHtml(doc.context)}</span>` : ""}
        <span class="result-meta">${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</span>
      </span>
      <span class="result-open" aria-hidden="true">→</span>`;
    item.addEventListener("click", () => openTicaretDocument(doc, item));
    resultList.append(item);
  });
}

function renderGeneralResults(data) {
  statusNote.hidden = true;
  resultList.innerHTML = "";
  state.total = data.total;
  resultCount.textContent = numberFormat.format(data.total);
  $("#resultContext").textContent = "genel mevzuat kaydı";
  updatePagination(data.total, data.page, data.has_next);

  if (!data.documents.length) {
    setStatus("Bu ölçütlerle mevzuat bulunamadı.", "Arama alanını değiştirin veya mevzuat türü filtresini kaldırın.");
    resultCount.textContent = "0";
    return;
  }

  data.documents.forEach((doc) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "result-item";
    const meta = [doc.type_label, doc.gazette_date ? `RG ${formatDate(doc.gazette_date)}` : "", doc.gazette_number ? `Sayı ${doc.gazette_number}` : ""].filter(Boolean);
    item.innerHTML = `
      <span class="result-node">${escapeHtml((doc.type || "MZV").slice(0, 4))}</span>
      <span><strong class="result-title">${escapeHtml(doc.title)}</strong><span class="result-meta">${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</span></span>
      <span class="result-open" aria-hidden="true">→</span>`;
    item.addEventListener("click", () => openGeneralDocument(doc, item));
    resultList.append(item);
  });
}

async function runTicaretSearch({ offset = 0 } = {}) {
  state.offset = offset;
  const query = queryInput.value.trim();
  const request = {
    query,
    content_kinds: state.activeKind ? [state.activeKind] : [],
    source_ids: $("#sourceFilter").value ? [$("#sourceFilter").value] : [],
    document_types: $("#documentType").value ? [$("#documentType").value] : [],
    year: $("#yearFilter").value || null,
    include_repealed: $("#includeRepealed").checked,
    offset,
    limit: state.limit,
  };
  resultsTitle.textContent = query ? `“${query}” dosyası` : (state.activeKind ? kindLabels[state.activeKind] : "Katalogdan son kayıtlar");
  setLoading();
  try {
    const data = await fetchJson("/api/ticaret/search", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    renderTicaretResults(data);
  } catch (error) {
    resultCount.textContent = "—";
    $("#resultContext").textContent = "arama başarısız";
    setStatus("Araştırma tamamlanamadı.", error.message || "Bağlantınızı kontrol edip yeniden deneyin.", true);
  }
}

async function runGeneralSearch({ page = 1 } = {}) {
  state.page = page;
  const query = queryInput.value.trim();
  const request = {
    query,
    mode: form.querySelector('input[name="generalMode"]:checked').value,
    type: $("#generalType").value,
    start_date: $("#startDate").value || null,
    end_date: $("#endDate").value || null,
    page,
    page_size: state.limit,
  };
  resultsTitle.textContent = query ? `“${query}” için genel mevzuat` : "Son yayımlanan mevzuat";
  setLoading();
  try {
    renderGeneralResults(await fetchJson("/api/search", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    }));
  } catch (error) {
    resultCount.textContent = "—";
    $("#resultContext").textContent = "arama başarısız";
    setStatus("Genel mevzuat araması tamamlanamadı.", error.message || "Bağlantınızı kontrol edip yeniden deneyin.", true);
  }
}

function runSearch(args = {}) {
  return state.scope === "ticaret" ? runTicaretSearch(args) : runGeneralSearch(args);
}

function citationRows(rows) {
  $("#citationSpine").innerHTML = rows.map(([label, value, warning]) => `
    <div class="citation-line${warning ? " warning" : ""}"><span>${escapeHtml(label)}</span><b>${escapeHtml(value || "—")}</b></div>`).join("");
}

function showReader(documentData, trigger) {
  state.currentDocument = documentData;
  state.currentTrigger = trigger;
  state.currentContent = "";
  state.currentOffset = 0;
  $("#evidenceEmpty").hidden = true;
  $("#evidenceDocument").hidden = false;
  reader.classList.add("open");
  reader.setAttribute("aria-hidden", "false");
  document.body.classList.add("reader-open");
  readerSearch.value = "";
  $("#readerWarning").hidden = true;
  loadMoreContent.hidden = true;
  if (window.innerWidth <= 1240) $(".panel-close").focus();
}

function setReaderContent(content, append = false) {
  state.currentContent = append ? `${state.currentContent}${content}` : content;
  readerContent.textContent = state.currentContent || "Bu kayıtta çıkarılabilir metin bulunamadı. Resmî kaynak bağlantısını açın.";
  $("#readerLength").textContent = `${numberFormat.format(state.currentContent.length)} karakter`;
}

async function openTicaretDocument(doc, trigger) {
  showReader(doc, trigger);
  $("#readerKind").textContent = `${kindLabels[doc.content_kind] || "Belge"} · ${String(doc.file_type || "web").toUpperCase()}`;
  $("#readerTitle").textContent = doc.title;
  $("#officialLink").href = safeUrl(doc.document_url || doc.source_page_url);
  citationRows([
    ["Katman", kindLabels[doc.content_kind]],
    ["Kaynak", sourceLabels[doc.source_id] || doc.source_id],
    ["Bölüm", doc.section],
    ["Tür / no", [doc.document_type, doc.number].filter(Boolean).join(" · ")],
    ["Tarih", doc.publication_date || doc.page_updated_at],
    ["Yürürlük", doc.is_repealed ? "Mülga / yürürlükten kaldırılmış" : "Kaynağından doğrulayın", doc.is_repealed],
  ]);
  readerContent.textContent = "Belge metni resmî kaynaktan çıkarılıyor…";
  $("#readerLength").textContent = "bekleniyor";
  try {
    const data = await fetchJson(`/api/ticaret/document/${encodeURIComponent(doc.id)}`);
    setReaderContent(data.content);
    state.currentOffset = data.offset + data.returned_characters;
    loadMoreContent.hidden = !data.truncated;
    if (data.warnings?.length) {
      $("#readerWarning").textContent = data.warnings.join(" · ");
      $("#readerWarning").hidden = false;
    }
  } catch (error) {
    readerContent.textContent = error.message || "Belge metni alınamadı. Resmî kaynak bağlantısını kullanın.";
    $("#readerLength").textContent = "metin alınamadı";
  }
}

async function openGeneralDocument(doc, trigger) {
  showReader(doc, trigger);
  $("#readerKind").textContent = "Genel mevzuat";
  $("#readerTitle").textContent = doc.title;
  $("#officialLink").href = safeUrl(doc.source_url || "https://www.mevzuat.gov.tr");
  citationRows([
    ["Katman", "Genel mevzuat"], ["Tür", doc.type_label], ["Mevzuat no", doc.number],
    ["Resmî Gazete", [doc.gazette_date && formatDate(doc.gazette_date), doc.gazette_number && `Sayı ${doc.gazette_number}`].filter(Boolean).join(" · ")],
  ]);
  readerContent.textContent = "Mevzuat metni resmî kaynaktan alınıyor…";
  $("#readerLength").textContent = "bekleniyor";
  try {
    const data = await fetchJson(`/api/document/${encodeURIComponent(doc.id)}`);
    setReaderContent(data.content);
  } catch (error) {
    readerContent.textContent = error.message || "Metin alınamadı.";
    $("#readerLength").textContent = "metin alınamadı";
  }
}

function closeReader() {
  reader.classList.remove("open");
  reader.setAttribute("aria-hidden", "true");
  document.body.classList.remove("reader-open");
  $("#evidenceDocument").hidden = true;
  $("#evidenceEmpty").hidden = false;
  state.currentTrigger?.focus();
}

async function loadCatalogStatus() {
  const liveState = $("#liveState");
  try {
    // Listing sources initializes the catalogue on a cold start; status is read
    // afterwards so the coverage ledger cannot display a stale zero snapshot.
    const sources = await fetchJson("/api/ticaret/sources");
    const status = await fetchJson("/api/ticaret/status");
    state.sourceData = sources;
    liveState.classList.add("online");
    liveState.querySelector("span").textContent = status.syncing ? "Katalog yenileniyor" : "Kaynaklar güncel";
    $("#syncBadge").textContent = status.syncing ? "eşitleniyor" : "canlı";
    $("#sourceCount").textContent = numberFormat.format(status.source_count);
    $("#pageCount").textContent = numberFormat.format(status.pages_scanned);
    $("#documentCount").textContent = numberFormat.format(status.document_count);
    $("#refreshCadence").textContent = `${Math.round(status.sync_interval_seconds / 3600)} sa.`;
    $("#lastSynced").textContent = status.last_synced_at ? `Son eşitleme: ${formatDate(status.last_synced_at, true)}` : "İlk eşitleme sürüyor.";
    $("#allCount").textContent = `${numberFormat.format(status.document_count)} canlı kayıt`;

    const sourceFilter = $("#sourceFilter");
    const selectedSource = sourceFilter.value;
    sourceFilter.replaceChildren(new Option("Tüm kaynaklar", ""));
    sources.sources.forEach((source) => {
      const option = document.createElement("option");
      option.value = source.id;
      option.textContent = `${sourceLabels[source.id] || source.id} (${numberFormat.format(source.documents)})`;
      sourceFilter.append(option);
    });
    if ([...sourceFilter.options].some((option) => option.value === selectedSource)) sourceFilter.value = selectedSource;
    $$(".layer[data-kind]").forEach((button) => {
      const kind = button.dataset.kind;
      if (!kind || !sources.layers[kind]) return;
      const small = button.querySelector("small");
      small.dataset.base ||= small.textContent;
      small.textContent = `${small.dataset.base} · ${numberFormat.format(sources.layers[kind].documents)}`;
    });
    if (status.syncing) window.setTimeout(loadCatalogStatus, 30000);
  } catch (error) {
    liveState.classList.add("error");
    liveState.querySelector("span").textContent = "Katalog hazırlanıyor";
    $("#syncBadge").textContent = "bekleniyor";
  }
}

function switchScope(scope) {
  if (scope === state.scope) return;
  state.scope = scope;
  $$("[data-scope]").forEach((button) => button.classList.toggle("active", button.dataset.scope === scope));
  $("#ticaretFilters").hidden = scope !== "ticaret";
  $("#generalFilters").hidden = scope !== "general";
  $(".workspace").classList.toggle("general-layout", scope === "general");
  $(".source-rail").hidden = scope === "general";
  $("#deskKicker").textContent = scope === "ticaret" ? "Ticaret Bakanlığı açık kaynakları" : "Adalet Bakanlığı mevzuat sistemi";
  $("#deskDescription").textContent = scope === "ticaret"
    ? "Mevzuat, devlet destekleri, dış ticaret verileri, ülke raporları ve ticaret müşavirliklerini tek katalogda araştırın."
    : "Türkiye Cumhuriyeti kanun, kararname, yönetmelik, genelge ve tebliğlerinde başlık, içerik veya numarayla arayın.";
  queryInput.placeholder = scope === "ticaret" ? "Örn. 4458 geçici ithalat, 5973 pazara giriş desteği…" : "Örn. Türk Ticaret Kanunu veya 6102…";
  closeReader();
  runSearch(scope === "ticaret" ? { offset: 0 } : { page: 1 });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch(state.scope === "ticaret" ? { offset: 0 } : { page: 1 });
});
$$('[data-query]').forEach((button) => button.addEventListener("click", () => {
  queryInput.value = button.dataset.query;
  runSearch(state.scope === "ticaret" ? { offset: 0 } : { page: 1 });
}));
$$('[data-scope]').forEach((button) => button.addEventListener("click", () => switchScope(button.dataset.scope)));
$$('.layer').forEach((button) => button.addEventListener("click", () => {
  state.activeKind = button.dataset.kind;
  $$('.layer').forEach((item) => item.classList.toggle("active", item === button));
  $("#sourceFilter").value = "";
  runTicaretSearch({ offset: 0 });
}));
prevPage.addEventListener("click", () => state.scope === "ticaret"
  ? runTicaretSearch({ offset: Math.max(0, state.offset - state.limit) })
  : runGeneralSearch({ page: Math.max(1, state.page - 1) }));
nextPage.addEventListener("click", () => state.scope === "ticaret"
  ? runTicaretSearch({ offset: state.offset + state.limit })
  : runGeneralSearch({ page: state.page + 1 }));
$$('[data-close-reader]').forEach((button) => button.addEventListener("click", closeReader));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && reader.classList.contains("open")) closeReader();
});

readerSearch.addEventListener("input", () => {
  const term = readerSearch.value.trim();
  if (!term || !state.currentContent) {
    readerContent.textContent = state.currentContent;
    return;
  }
  const lower = state.currentContent.toLocaleLowerCase("tr-TR");
  const index = lower.indexOf(term.toLocaleLowerCase("tr-TR"));
  if (index < 0) {
    readerContent.textContent = state.currentContent;
    return;
  }
  readerContent.innerHTML = `${escapeHtml(state.currentContent.slice(0, index))}<mark>${escapeHtml(state.currentContent.slice(index, index + term.length))}</mark>${escapeHtml(state.currentContent.slice(index + term.length))}`;
  requestAnimationFrame(() => readerContent.querySelector("mark")?.scrollIntoView({ block: "center" }));
});

loadMoreContent.addEventListener("click", async () => {
  if (!state.currentDocument || state.scope !== "ticaret") return;
  loadMoreContent.disabled = true;
  loadMoreContent.textContent = "Devamı alınıyor…";
  try {
    const data = await fetchJson(`/api/ticaret/document/${encodeURIComponent(state.currentDocument.id)}?offset=${state.currentOffset}`);
    setReaderContent(data.content, true);
    state.currentOffset = data.offset + data.returned_characters;
    loadMoreContent.hidden = !data.truncated;
  } catch (error) {
    showToast(error.message || "Belgenin devamı alınamadı.");
  } finally {
    loadMoreContent.disabled = false;
    loadMoreContent.textContent = "Belgenin devamını getir";
  }
});

$("#copyCitation").addEventListener("click", () => {
  if (!state.currentDocument) return;
  const doc = state.currentDocument;
  const citation = state.scope === "ticaret"
    ? `${doc.title}. ${sourceLabels[doc.source_id] || doc.source_id}, T.C. Ticaret Bakanlığı. ${doc.publication_date || doc.page_updated_at || "Tarih belirtilmemiş"}. ${doc.document_url || doc.source_page_url}`
    : `${doc.title}. ${doc.type_label || "Mevzuat"}${doc.number ? `, No ${doc.number}` : ""}. ${doc.gazette_date || ""} ${doc.source_url || "https://www.mevzuat.gov.tr"}`;
  copyText(citation, "Belge atfı kopyalandı.");
});
$("#copyMcp").addEventListener("click", () => copyText(`${window.location.origin}/mcp`, "MCP adresi kopyalandı."));

const savedTheme = localStorage.getItem("ticaret-bilgi-theme");
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$("#themeToggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("ticaret-bilgi-theme", next);
});

loadCatalogStatus();
runTicaretSearch({ offset: 0 });
