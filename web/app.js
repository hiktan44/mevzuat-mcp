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
  customsImageData: null,
  customsVisionStatus: "idle",
  customsVisionResult: null,
  customsClassificationResult: null,
  customsAutoGtip: null,
  customsGtipSelectionConfirmed: false,
  customsPendingSubmit: false,
  tariffRateSources: {},
  consultationBadge: 0,
  customsExactGtipConfirmed: false,
  customsApplyingTariffSelection: false,
  customsTariffTree: null,
  customsSelectedCandidate: null,
  customsClassificationAnswers: {},
  auth: null,
  currentCustomsResult: null,
  selectedConsultant: null,
  consultants: [],
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
  resmi_gazete_guncel: "Resmî Gazete / güncel mevzuat",
  gumruk: "Gümrük işlemleri",
  ihracat: "İhracat",
  ithalat: "İthalat",
  ithalat_duyurular: "İthalat Genel Müdürlüğü duyuruları",
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
  musavirlik_blog_guncel: "Müşavirlik güncel bilgileri",
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

function nullableNumber(selector) {
  const value = $(selector)?.value?.trim();
  if (!value) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
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

function activeTicaretFilters() {
  const chips = [];
  if (state.activeKind) chips.push({ key: "kind", label: `Katman: ${kindLabels[state.activeKind] || state.activeKind}` });
  const source = $("#sourceFilter");
  if (source.value) chips.push({ key: "source", label: `Kaynak: ${source.selectedOptions[0]?.textContent || source.value}` });
  if ($("#documentType").value) chips.push({ key: "type", label: `Belge türü: ${$("#documentType").value}` });
  if ($("#yearFilter").value) chips.push({ key: "year", label: `Yıl: ${$("#yearFilter").value}` });
  if (!$("#includeRepealed").checked) chips.push({ key: "repealed", label: "Mülga kayıtlar gizli" });
  return chips;
}

function renderActiveFilterChips() {
  const chips = activeTicaretFilters();
  const container = statusNote.querySelector("p");
  if (!chips.length) { container.insertAdjacentHTML("beforeend", " Şu anda hiçbir filtre uygulanmıyor."); return; }
  container.insertAdjacentHTML("beforeend", `<span class="filter-chips">${chips.map((chip) => `<button type="button" class="filter-chip" data-clear-filter="${chip.key}"><span>${escapeHtml(chip.label)}</span><i aria-hidden="true">×</i></button>`).join("")}${chips.length > 1 ? '<button type="button" class="filter-chip clear-all" data-clear-filter="all">Tümünü kaldır</button>' : ""}</span>`);
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
    setStatus("Bu dosyada kayıt bulunamadı.", "Daha kısa bir ifade deneyin veya aşağıdaki filtrelerden birini kaldırın.");
    renderActiveFilterChips();
    resultCount.textContent = "0";
    return;
  }

  data.documents.forEach((doc) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `result-item kind-${escapeHtml(doc.content_kind || "other")}${doc.is_repealed ? " repealed" : ""}`;
    item.dataset.kind = doc.content_kind || "other";
    const meta = [doc.document_type || kindLabels[doc.content_kind], doc.number ? `No ${doc.number}` : ""].filter(Boolean);
    item.innerHTML = `
      <span class="result-node" aria-hidden="true"></span>
      <span class="result-main">
        <strong class="result-title">${escapeHtml(doc.title)}</strong>
        <span class="result-subline">${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</span>
        ${doc.context ? `<span class="result-context">${escapeHtml(doc.context)}</span>` : ""}
      </span>
      <span class="result-source">${escapeHtml(sourceLabels[doc.source_id] || doc.source_id)}</span>
      <span class="result-date">${escapeHtml(doc.publication_date || doc.page_updated_at || "—")}</span>
      <span class="result-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m9 5 7 7-7 7"/></svg></span>`;
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
    const meta = [doc.type_label, doc.number ? `No ${doc.number}` : "", doc.gazette_number ? `RG ${doc.gazette_number}` : ""].filter(Boolean);
    item.innerHTML = `
      <span class="result-node" aria-hidden="true"></span>
      <span class="result-main"><strong class="result-title">${escapeHtml(doc.title)}</strong><span class="result-subline">${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</span></span>
      <span class="result-source">${escapeHtml(doc.type_label || "Mevzuat")}</span>
      <span class="result-date"${doc.date_warning ? ` title="${escapeHtml(doc.date_warning)}"` : ""}>${doc.gazette_date ? `${escapeHtml(formatDate(doc.gazette_date))}${doc.date_warning ? " ⚠" : ""}` : "—"}</span>
      <span class="result-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m9 5 7 7-7 7"/></svg></span>`;
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
  $("#citationSpine").innerHTML = rows.map(([label, value, warning, url]) => {
    const renderedValue = url
      ? `<a href="${safeUrl(url)}" target="_blank" rel="noreferrer">${escapeHtml(value || "Resmî sayfayı aç")}<span aria-hidden="true">↗</span></a>`
      : `<b>${escapeHtml(value || "—")}</b>`;
    return `<div class="citation-line${warning ? " warning" : ""}"><span>${escapeHtml(label)}</span>${renderedValue}</div>`;
  }).join("");
}

function renderOfficialLinks(doc, resolvedUrl = "") {
  const candidates = [
    [doc.document_url, doc.file_type && doc.file_type !== "html" && doc.file_type !== "link" ? `Belgeyi aç · ${String(doc.file_type).toUpperCase()}` : "Belge sayfasını aç", "Seçilen kayıt"],
    [doc.source_page_url, "Yayımlandığı sayfayı aç", sourceLabels[doc.source_id] || "Resmî kaynak"],
    [resolvedUrl, "Okunan resmî adresi aç", "Tam metnin alındığı adres"],
  ];
  const seen = new Set();
  const links = candidates.filter(([url]) => {
    if (!url) return false;
    const href = safeUrl(url || "");
    if (href === "#" || seen.has(href)) return false;
    seen.add(href);
    return true;
  });
  $("#readerLinks").innerHTML = links.map(([url, title, description]) => `
    <a href="${safeUrl(url)}" target="_blank" rel="noreferrer">
      <span><b>${escapeHtml(title)}</b><small>${escapeHtml(description)}</small></span><i aria-hidden="true">↗</i>
    </a>`).join("");
  $(".reader-links").hidden = links.length === 0;
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
  $("#readerOutline").hidden = true;
  $("#readerOutlineNav").innerHTML = "";
  $("#readerWarning").hidden = true;
  loadMoreContent.hidden = true;
  $$(".result-item").forEach((item) => item.classList.toggle("selected", item === trigger));
  if (window.innerWidth <= 1260) $(".panel-close").focus();
}

function highlightReaderText(value, term = "") {
  if (!term) return escapeHtml(value);
  const source = String(value);
  const lower = source.toLocaleLowerCase("tr-TR");
  const needle = term.toLocaleLowerCase("tr-TR");
  if (!needle) return escapeHtml(source);
  let cursor = 0;
  let output = "";
  while (cursor < source.length) {
    const index = lower.indexOf(needle, cursor);
    if (index < 0) {
      output += escapeHtml(source.slice(cursor));
      break;
    }
    output += `${escapeHtml(source.slice(cursor, index))}<mark>${escapeHtml(source.slice(index, index + term.length))}</mark>`;
    cursor = index + term.length;
  }
  return output;
}

function readerReferenceKey(value) {
  return String(value).trim().replace(/\s+/g, " ").toLocaleLowerCase("tr-TR");
}

function readerBlocks(content) {
  const normalised = String(content || "")
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t]+(?=(?:GEÇİCİ\s+)?MADDE\s+\d+[A-Za-z]?\s*[-–—])/giu, "\n");
  const blocks = [];
  normalised.split("\n").forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) return;
    const article = line.match(/^((?:GEÇİCİ\s+)?MADDE\s+\d+[A-Za-z]?)\s*[-–—]\s*(.*)$/iu);
    if (article) {
      blocks.push({ type: "heading", text: article[1], article: true });
      if (article[2]) blocks.push({ type: "paragraph", text: article[2] });
      return;
    }
    const numberedSection = /^(?:(?:BİRİNCİ|İKİNCİ|ÜÇÜNCÜ|DÖRDÜNCÜ|BEŞİNCİ|ALTINCI|YEDİNCİ|SEKİZİNCİ|DOKUZUNCU|ONUNCU)\s+)?(?:KISIM|BÖLÜM|FASIL)\b/iu.test(line);
    const appendixHeading = /^(?:EK|CETVEL|TABLO)\s*[-–—:]?\s*[A-Z0-9/]+(?:\s|$)/iu.test(line) && line.length <= 120;
    blocks.push({ type: numberedSection || appendixHeading ? "heading" : "paragraph", text: line, article: false });
  });
  return blocks;
}

function formatReaderText(value, term = "") {
  const source = String(value);
  const tokenPattern = /https?:\/\/[^\s<>"']+/giu;
  let cursor = 0;
  let output = "";
  for (const match of source.matchAll(tokenPattern)) {
    const index = match.index ?? 0;
    output += highlightReaderText(source.slice(cursor, index), term);
    let token = match[0];
    if (/^https?:\/\//iu.test(token)) {
      const trailing = token.match(/[),.;:]+$/u)?.[0] || "";
      if (trailing) token = token.slice(0, -trailing.length);
      output += `<a class="reader-external-link" href="${safeUrl(token)}" target="_blank" rel="noreferrer">${highlightReaderText(token, term)}</a>${escapeHtml(trailing)}`;
    }
    cursor = index + match[0].length;
  }
  output += highlightReaderText(source.slice(cursor), term);
  return output;
}

function renderReaderContent(term = "") {
  const content = state.currentContent || "";
  if (!content) {
    readerContent.textContent = "Bu kayıtta çıkarılabilir metin bulunamadı. Resmî kaynak bağlantısını açın.";
    $("#readerOutline").hidden = true;
    return;
  }

  const blocks = readerBlocks(content);
  const groups = [];
  let current = { id: "reader-preamble", title: "Belge başlangıcı", outline: false, blocks: [] };
  let sectionIndex = 0;
  blocks.forEach((block) => {
    if (block.type !== "heading") {
      current.blocks.push(block);
      return;
    }
    if (current.blocks.length || current.outline) groups.push(current);
    sectionIndex += 1;
    const articleKey = block.article ? readerReferenceKey(block.text) : "";
    const id = block.article
      ? `reader-${articleKey.replaceAll(" ", "-").replaceAll("ç", "c").replaceAll("ı", "i").replaceAll("ş", "s").replaceAll("ğ", "g").replaceAll("ü", "u").replaceAll("ö", "o")}`
      : `reader-section-${sectionIndex}`;
    current = { id, title: block.text, outline: true, blocks: [] };
  });
  if (current.blocks.length || current.outline) groups.push(current);

  const outlineGroups = groups.filter((group) => group.outline);
  const outline = $("#readerOutline");
  outline.hidden = outlineGroups.length === 0;
  $("#readerOutlineCount").textContent = `${numberFormat.format(outlineGroups.length)} bölüm`;
  $("#readerOutlineNav").innerHTML = outlineGroups.map((group) => `
    <button type="button" data-reader-anchor="${escapeHtml(group.id)}"><span>${escapeHtml(group.title)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg></button>`).join("");

  readerContent.innerHTML = groups.map((group) => {
    const body = group.blocks.map((block) => `<p>${formatReaderText(block.text, term)}</p>`).join("");
    if (!group.outline) return `<div class="reader-preamble">${body}</div>`;
    return `<details class="reader-section" id="${escapeHtml(group.id)}" tabindex="-1" open>
      <summary><span>${highlightReaderText(group.title, term)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
      <div class="reader-section-body">${body || '<p class="reader-empty-section">Bu başlık altında ayrı metin bulunamadı.</p>'}</div>
    </details>`;
  }).join("");
}

function setReaderContent(content, append = false) {
  state.currentContent = append ? `${state.currentContent}\n${content}` : content;
  renderReaderContent(readerSearch.value.trim());
  $("#readerLength").textContent = `${numberFormat.format(state.currentContent.length)} karakter`;
}

async function openTicaretDocument(doc, trigger) {
  showReader(doc, trigger);
  $("#readerKind").textContent = `${kindLabels[doc.content_kind] || "Belge"} · ${String(doc.file_type || "web").toUpperCase()}`;
  $("#readerTitle").textContent = doc.title;
  $("#officialLink").href = safeUrl(doc.document_url || doc.source_page_url);
  renderOfficialLinks(doc);
  citationRows([
    ["Katman", kindLabels[doc.content_kind]],
    ["Kaynak", sourceLabels[doc.source_id] || doc.source_id, false, doc.source_page_url],
    ["Bölüm", doc.section, false, doc.source_page_url],
    ["Tür / no", [doc.document_type, doc.number].filter(Boolean).join(" · "), false, doc.document_url],
    ["Tarih", doc.publication_date || doc.page_updated_at, false, doc.source_page_url],
    ["Yürürlük", doc.is_repealed ? "Mülga / yürürlükten kaldırılmış" : "Kaynağından doğrulayın", doc.is_repealed],
  ]);
  readerContent.textContent = "Belge metni resmî kaynaktan çıkarılıyor…";
  $("#readerLength").textContent = "bekleniyor";
  try {
    const data = await fetchJson(`/api/ticaret/document/${encodeURIComponent(doc.id)}`);
    setReaderContent(data.content);
    renderOfficialLinks(doc, data.resolved_url);
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
  renderOfficialLinks({
    ...doc,
    document_url: doc.source_url || "https://www.mevzuat.gov.tr",
    source_page_url: doc.source_url || "https://www.mevzuat.gov.tr",
    source_id: "genel_mevzuat",
    file_type: "html",
  });
  citationRows([
    ["Katman", "Genel mevzuat"], ["Tür", doc.type_label, false, doc.source_url], ["Mevzuat no", doc.number, false, doc.source_url],
    ["Resmî Gazete", [doc.gazette_date && formatDate(doc.gazette_date), doc.gazette_number && `Sayı ${doc.gazette_number}`].filter(Boolean).join(" · "), false, doc.source_url],
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
  $$(".result-item").forEach((item) => item.classList.remove("selected"));
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
    const priorityHours = Math.max(1, Math.round(status.sync_interval_seconds / 3600));
    const fullHours = Math.max(priorityHours, Math.round((status.full_sync_interval_seconds || status.sync_interval_seconds) / 3600));
    $("#refreshCadence").textContent = `${priorityHours} sa. / tam ${fullHours} sa.`;
    $("#latestGazetteDate").textContent = status.latest_official_gazette_date
      ? formatDate(status.latest_official_gazette_date)
      : "—";
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
    $$(".source-link[data-kind]").forEach((button) => {
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

async function loadAuthState() {
  try {
    const response = await fetch("/api/auth/me", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const auth = await response.json();
    state.auth = auth;
    if (!auth.authenticated || !auth.user) return;
    const firstName = String(auth.user.name || auth.user.email || "Hesabım").split(" ")[0];
    $("#appLogin").hidden = true;
    $("#appAccountButton").hidden = false;
    $("#appAccountButton").textContent = `${firstName} · Hesabım`;
    refreshConsultationBadge();
    if (new URLSearchParams(location.search).get("account")) openAccount();
  } catch (_) {
    // The application remains usable as a guest if account state is unavailable.
  }
}

const quotaLabels = { vision: "Görsel analiz", classification: "GTİP adayı", precheck: "Ön değerlendirme", dossier: "Kanıt dosyası" };

function switchAccountTab(tab) {
  $$('[data-account-tab]').forEach((button) => button.classList.toggle("active", button.dataset.accountTab === tab));
  $$('[data-account-panel]').forEach((panel) => { panel.hidden = panel.dataset.accountPanel !== tab; });
  if (tab === "dossiers") loadDossiers();
}

function renderAccount(auth) {
  const account = auth.account;
  $("#accountIdentity").textContent = `${auth.user.name || "Kullanıcı"} · ${auth.user.email}`;
  $("#currentPlanName").textContent = account.plan.name;
  $("#currentPlanStatus").textContent = `${account.period} kullanım dönemi · ${account.subscription.status}`;
  $("#adminLink").hidden = !account.is_admin;
  $("#manageBilling").hidden = !(
    account.subscription.provider === "stripe"
    && ["active", "pending", "past_due"].includes(account.subscription.status)
  );
  $("#quotaGrid").innerHTML = Object.entries(account.quotas).map(([key, quota]) => {
    const percent = quota.limit == null ? 0 : Math.min(100, Math.round((quota.used / Math.max(1, quota.limit)) * 100));
    return `<article class="quota-card"><header><b>${escapeHtml(quotaLabels[key] || key)}</b><span>${quota.limit == null ? `${quota.used} / sınırsız` : `${quota.used} / ${quota.limit}`}</span></header><div class="quota-track"><i style="width:${percent}%"></i></div></article>`;
  }).join("");
}

async function openAccount(tab = "summary") {
  if (!state.auth?.authenticated) {
    location.href = "/auth/google";
    return;
  }
  const dialog = $("#accountDialog");
  if (!dialog.open) dialog.showModal();
  switchAccountTab(tab);
  renderAccount(state.auth);
  try {
    const [account, plans] = await Promise.all([fetchJson("/api/account"), fetchJson("/api/plans")]);
    state.auth.account = account;
    state.auth.billing_enabled = plans.billing_enabled;
    state.salesEmail = plans.sales_email || state.salesEmail;
    renderAccount(state.auth);
    renderPlans(plans.plans, plans.billing_enabled);
  } catch (error) { showToast(error.message); }
}

function renderPlans(plans, billingEnabled) {
  $("#pricingGrid").innerHTML = plans.map((plan) => {
    const monthly = plan.monthly_price_try == null ? "Teklif" : plan.monthly_price_try === 0 ? "Ücretsiz" : `${numberFormat.format(plan.monthly_price_try)} TL`;
    const purchasable = ["expert", "team"].includes(plan.code);
    const salesHref = `mailto:${escapeHtml(state.salesEmail || "")}?subject=${encodeURIComponent(`Ticaret Bilgi Masası · ${plan.name} paketi`)}`;
    const salesLink = `<a class="price-link" href="${salesHref}">Satış ekibiyle görüşün</a>`;
    const actions = purchasable
      ? (billingEnabled
        ? `<button type="button" data-buy-plan="${escapeHtml(plan.code)}" data-buy-cycle="monthly">Aylık başlat</button><button class="yearly" type="button" data-buy-plan="${escapeHtml(plan.code)}" data-buy-cycle="yearly">Yıllık · ${numberFormat.format(plan.yearly_price_try)} TL + KDV</button>`
        : `<p class="price-soon">Çevrim içi ödeme yakında açılıyor. Yıllık: ${numberFormat.format(plan.yearly_price_try)} TL + KDV.</p>${salesLink}`)
      : plan.code === "starter" ? '<button type="button" disabled>Mevcut ücretsiz paket</button>' : salesLink;
    return `<article class="price-card${plan.code === "expert" ? " featured" : ""}"><span>${escapeHtml(plan.code)}</span><h3>${escapeHtml(plan.name)}</h3><div class="price">${escapeHtml(monthly)}${plan.monthly_price_try ? "<small> + KDV / ay</small>" : ""}</div><ul>${plan.features.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><div class="price-actions">${actions}</div></article>`;
  }).join("");
}

async function loadDossiers() {
  const target = $("#dossierList");
  target.innerHTML = "<p>Kanıt dosyaları yükleniyor…</p>";
  try {
    const data = await fetchJson("/api/dossiers");
    target.innerHTML = data.items.length ? data.items.map((item) => `<article class="dossier-item"><div><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.gtip || "GTİP yok")} · ${escapeHtml(item.origin_country || "menşe yok")} · ${escapeHtml(formatDate(item.checked_at, true))}</small></div><div class="dossier-actions"><a href="/api/dossiers/${encodeURIComponent(item.id)}?download=1">JSON indir</a><button type="button" data-delete-dossier="${escapeHtml(item.id)}">Sil</button></div></article>`).join("") : "<p>Henüz sunucuda kayıtlı kanıt dosyanız yok.</p>";
  } catch (error) { target.innerHTML = `<p>${escapeHtml(error.message)}</p>`; }
}

statusNote.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-clear-filter]");
  if (!chip) return;
  const key = chip.dataset.clearFilter;
  const clear = {
    kind: () => selectSourceKind("", { run: false, focus: false }),
    source: () => { $("#sourceFilter").value = ""; },
    type: () => { $("#documentType").value = ""; },
    year: () => { $("#yearFilter").value = ""; },
    repealed: () => { $("#includeRepealed").checked = true; },
  };
  if (key === "all") Object.values(clear).forEach((fn) => fn()); else clear[key]?.();
  runTicaretSearch();
});

$("#appAccountButton").addEventListener("click", () => openAccount());
$("#closeAccount").addEventListener("click", () => $("#accountDialog").close());
$("#accountDialog").addEventListener("click", (event) => { if (event.target === $("#accountDialog")) $("#accountDialog").close(); });
$$('[data-account-tab]').forEach((button) => button.addEventListener("click", () => switchAccountTab(button.dataset.accountTab)));
$("#refreshDossiers").addEventListener("click", loadDossiers);
$("#dossierList").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-dossier]");
  if (!button || !confirm("Bu kanıt dosyası kalıcı olarak silinsin mi?")) return;
  try {
    await fetchJson(`/api/dossiers/${encodeURIComponent(button.dataset.deleteDossier)}`, { method: "DELETE" });
    await loadDossiers();
    try { state.auth.account = await fetchJson("/api/account"); renderAccount(state.auth); } catch { /* kota görünümü bir sonraki açılışta yenilenir */ }
    showToast("Kanıt dosyası silindi; kanıt dosyası kotanız güncellendi.");
  } catch (error) { showToast(error.message); }
});

$("#pricingGrid").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-buy-plan]");
  if (!button || button.disabled) return;
  button.disabled = true;
  try {
    const checkout = await fetchJson("/api/billing/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      plan_code: button.dataset.buyPlan, billing_cycle: button.dataset.buyCycle,
    }) });
    const target = new URL(checkout.checkout_url);
    if (target.protocol !== "https:" || target.hostname !== "checkout.stripe.com") throw new Error("Stripe yönlendirme adresi doğrulanamadı.");
    location.assign(target.href);
  } catch (error) { showToast(error.message); }
  finally { button.disabled = false; }
});
$("#manageBilling").addEventListener("click", async (event) => {
  event.currentTarget.disabled = true;
  try {
    const result = await fetchJson("/api/billing/portal", { method: "POST" });
    const target = new URL(result.portal_url);
    if (target.protocol !== "https:" || target.hostname !== "billing.stripe.com") throw new Error("Stripe abonelik adresi doğrulanamadı.");
    location.assign(target.href);
  } catch (error) { showToast(error.message); }
  finally { event.currentTarget.disabled = false; }
});
$("#deleteAccount").addEventListener("click", async () => {
  if (!confirm("Hesabınız, abonelik kaydınız, kullanım geçmişiniz ve kanıt dosyalarınız kalıcı olarak silinsin mi?")) return;
  try { await fetchJson("/api/account", { method: "DELETE" }); location.href = "/?account=deleted"; }
  catch (error) { showToast(error.message); }
});

function switchScope(scope) {
  if (scope === state.scope) return;
  state.scope = scope;
  $$("[data-scope]").forEach((button) => button.classList.toggle("active", button.dataset.scope === scope));
  $("#ticaretFilters").hidden = scope !== "ticaret";
  $("#generalFilters").hidden = scope !== "general";
  $(".app-shell").classList.toggle("general-layout", scope === "general");
  $(".app-shell").classList.toggle("customs-layout", scope === "customs");
  $(".source-sidebar").hidden = scope !== "ticaret";
  $("#researchWorkspace").hidden = scope === "customs";
  $("#customsWorkspace").hidden = scope !== "customs";
  reader.hidden = scope === "customs";
  if (scope === "customs") {
    closeReader();
    $("#customsQuestion").focus();
    return;
  }
  reader.hidden = false;
  queryInput.placeholder = scope === "ticaret" ? "Gümrük, ithalat, ihracat, destek veya ülke raporu ara" : "Kanun adı, mevzuat numarası veya içerik ara";
  closeReader();
  runSearch(scope === "ticaret" ? { offset: 0 } : { page: 1 });
}

function selectSourceKind(kind, { run = true, focus = true } = {}) {
  state.activeKind = kind;
  const selected = $(`.source-link[data-kind="${kind}"]`) || $('.source-link[data-kind=""]');
  $$('.source-link').forEach((item) => item.classList.toggle("active", item === selected));
  $$('.quick-route').forEach((item) => {
    const active = item.dataset.quickAction === kind;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", active ? "true" : "false");
  });
  $("#sourceFilter").value = "";
  if (focus) queryInput.focus();
  if (run) runTicaretSearch({ offset: 0 });
}

$$('.quick-route').forEach((button) => button.addEventListener("click", () => {
  const action = button.dataset.quickAction;
  if (action === "customs") {
    switchScope("customs");
    window.setTimeout(() => $("#productImage")?.focus(), 0);
    return;
  }
  if (state.scope !== "ticaret") switchScope("ticaret");
  selectSourceKind(action);
}));

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch(state.scope === "ticaret" ? { offset: 0 } : { page: 1 });
});
$$('[data-scope]').forEach((button) => button.addEventListener("click", () => switchScope(button.dataset.scope)));
$$('.source-link').forEach((button) => button.addEventListener("click", () => {
  selectSourceKind(button.dataset.kind);
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
  renderReaderContent(readerSearch.value.trim());
  requestAnimationFrame(() => readerContent.querySelector("mark")?.scrollIntoView({ behavior: "smooth", block: "center" }));
});

reader.addEventListener("click", (event) => {
  const control = event.target.closest("[data-reader-anchor]");
  if (!control || !reader.contains(control)) return;
  const target = document.getElementById(control.dataset.readerAnchor);
  if (!target) return;
  const section = target.matches("details") ? target : target.closest("details.reader-section");
  if (section) section.open = true;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.focus({ preventScroll: true });
});

$("#expandAllSections").addEventListener("click", () => {
  $$("#readerContent details.reader-section").forEach((section) => { section.open = true; });
});

$("#collapseAllSections").addEventListener("click", () => {
  $$("#readerContent details.reader-section").forEach((section) => { section.open = false; });
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

function customsSourceMap(data) {
  return new Map((data.sources || []).map((source) => [source.id, source]));
}

function citationChips(citations, sourceMap) {
  if (!citations?.length) return "";
  return `<div class="citation-chips">${citations.map((id) => {
    const source = sourceMap.get(id);
    return source ? `<a href="${safeUrl(source.url)}" target="_blank" rel="noreferrer">[${escapeHtml(id)}]</a>` : "";
  }).join("")}</div>`;
}

function renderFindings(items, sourceMap, type = "finding") {
  if (!items?.length) return '<p class="missing-list">Bu başlıkta doğrulanmış bulgu üretilemedi.</p>';
  return `<div class="finding-grid">${items.map((item) => `
    <article class="finding-card ${escapeHtml(item.status)}">
      <span>${escapeHtml(item.status)}</span>
      <b>${escapeHtml(item.name)}</b>
      ${type === "tax" && item.rate ? `<p><strong>Oran:</strong> ${escapeHtml(item.rate)}${item.basis ? ` · ${escapeHtml(item.basis)}` : ""}</p>` : ""}
      <p>${escapeHtml(item.explanation)}</p>
      ${citationChips(item.citations, sourceMap)}
    </article>`).join("")}</div>`;
}

function renderCost(cost) {
  if (!cost) return '<p class="missing-list">Fatura bedeli girilmediği için kıymet hesabı yapılmadı.</p>';
  const currency = escapeHtml(cost.currency || "");
  const amount = (value) => value == null ? "Doğrulanmış oran eksik" : `${numberFormat.format(value)} ${currency}`;
  return `<table class="cost-table"><tbody>
    <tr><td>Tahmini gümrük kıymeti</td><td>${amount(cost.customs_value_estimate)}</td></tr>
    <tr><td>Gümrük vergisi</td><td>${amount(cost.customs_duty)}</td></tr>
    <tr><td>İlave vergi</td><td>${amount(cost.additional_duty)}</td></tr>
    <tr><td>KDV matrahı tahmini</td><td>${amount(cost.vat_base_estimate)}</td></tr>
    <tr><td>KDV</td><td>${amount(cost.vat)}</td></tr>
    <tr><td>Bilinen kalemlerle toplam</td><td>${amount(cost.known_landed_total)}</td></tr>
  </tbody></table><p class="rate-warning">${escapeHtml(cost.note)}</p>`;
}

function renderMeasureCoverage(coverage) {
  const labels = {
    customs_duty: "Gümrük vergisi",
    additional_duty: "İGV",
    additional_financial_liability: "Ek mali yükümlülük",
    anti_dumping: "Damping / sübvansiyon",
    surveillance: "Gözetim",
    safeguard: "Korunma önlemi",
    tariff_quota: "Tarife kontenjanı",
    vat: "KDV",
    kkdf: "KKDF",
    sct: "ÖTV",
  };
  const statusLabels = {
    verified_snapshot: "Canlı tabloda doğrulandı",
    partial_snapshot: "Kısmi kaynak",
    not_integrated: "Ayrıca doğrulanmalı",
    user_confirmation_required: "Doğrulanmış giriş gerekli",
  };
  const entries = Object.entries(coverage || {});
  if (!entries.length) return "";
  return `<div class="measure-coverage">${entries.map(([key, item]) => `<article data-state="${escapeHtml(item.status)}"><b>${escapeHtml(labels[key] || key)}</b><span>${escapeHtml(statusLabels[item.status] || item.status)}</span><p>${escapeHtml(item.note)}</p></article>`).join("")}</div>`;
}

function renderExpertReviewPacket(packet) {
  if (!packet) return "";
  const labels = { BTB: "Bağlayıcı Tarife Bilgisi", "gümrük_müşaviri": "Yetkili gümrük müşaviri", "yetkili_kurum": "Yetkili kurum" };
  const hashes = [
    ...(packet.tariff_snapshot_sha256 || []),
    ...(packet.control_document_sha256 || []),
    ...(packet.classification_snapshot_sha256 || []),
  ];
  return `<section class="answer-section expert-review" data-risk="${escapeHtml(packet.risk_level)}"><h3>Uzman / BTB inceleme dosyası · ${escapeHtml(packet.risk_level)}</h3>
    <div class="expert-review-grid"><div><b>İnceleme kanalları</b><p>${(packet.review_types || []).map((item) => escapeHtml(labels[item] || item)).join(" · ") || "Ek inceleme gerekmiyor"}</p></div><div><b>Tarife yolu</b><p>${(packet.classification_path || []).map((item) => `<code>${escapeHtml(item)}</code>`).join(" › ") || "Kesinleşmedi"}</p></div></div>
    <ul class="missing-list">${(packet.reasons || ["Yüksek risk nedeni bildirilmedi."]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    ${(packet.questions_for_reviewer || []).length ? `<details class="expert-questions"><summary>Uzman için hazırlanmış sorular</summary><ol>${packet.questions_for_reviewer.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></details>` : ""}
    ${hashes.length ? `<p class="expert-hashes"><b>Kanıt izleri:</b> ${hashes.map((item) => `<code title="${escapeHtml(item)}">${escapeHtml(item.slice(0, 12))}…</code>`).join(" ")}</p>` : ""}
    <button class="secondary-action" id="downloadExpertPacket" type="button">Müşavir / BTB dosyasını JSON indir</button></section>`;
}

function renderCustomsResult(data) {
  state.currentCustomsResult = data;
  const sourceMap = customsSourceMap(data);
  const statusLabels = {
    preliminary: "Ön değerlendirme",
    needs_information: "Bilgi gerekli",
    insufficient_evidence: "Kanıt yetersiz",
    evidence_only: "Yalnız kanıt paketi",
  };
  const warningStatus = data.status !== "preliminary";
  const candidates = data.candidate_gtips?.length ? `
    <div class="candidate-grid">${data.candidate_gtips.map((item) => `
      <article class="candidate-card"><code>${escapeHtml(item.code)}</code><b>${escapeHtml(item.confidence)} güven</b><p>${escapeHtml(item.explanation)}</p>${citationChips(item.citations, sourceMap)}</article>`).join("")}</div>`
    : '<p class="missing-list">Kanıtla desteklenen aday kod üretilemedi. Fotoğraf tek başına kesin GTİP değildir.</p>';
  const sources = (data.sources || []).map((source) => `
    <a href="${safeUrl(source.url)}" target="_blank" rel="noreferrer">
      <code>[${escapeHtml(source.id)}]</code><span><b>${escapeHtml(source.title)}</b><small>${escapeHtml(source.authority)}${source.fetch_warning ? ` · ${escapeHtml(source.fetch_warning)}` : ""}</small></span>
    </a>`).join("");
  $("#customsOutput").innerHTML = `
    <article class="answer-sheet">
      <header class="answer-head">
        <span class="answer-status${warningStatus ? " warning" : ""}">${escapeHtml(statusLabels[data.status] || data.status)}</span>
        <div><h2>İthalat ön değerlendirme dosyası</h2><p>${escapeHtml(data.summary)}</p></div>
        <time>${escapeHtml(formatDate(data.as_of, true))}</time>
      </header>
      <section class="answer-section"><h3>Aday GTİP / CN kodları</h3>${candidates}</section>
      ${data.tariff_lookup ? `<section class="answer-section"><h3>Resmî tarife snapshot eşleşmesi</h3>${tariffMatchSummary(data.tariff_lookup)}${renderMeasureCoverage(data.tariff_lookup.measure_coverage)}<table class="evidence-table"><thead><tr><th>GTİP / Önlem</th><th>Oran</th><th>Menşe sütunu</th><th>Kaynak satırı</th><th>Kanıt</th></tr></thead><tbody>${tariffRows(data.tariff_lookup.measures)}</tbody></table>${applyRatesButton(data.tariff_lookup, "precheck")}${(data.tariff_lookup.warnings || []).length ? `<div class="result-caution">${data.tariff_lookup.warnings.map((item) => escapeHtml(item)).join(" · ")}</div>` : ""}</section>` : ""}
      ${data.origin_documents ? `<section class="answer-section"><h3>Menşe belgeleri · ${escapeHtml(data.origin_documents.regime_name)}</h3><ul class="missing-list">${(data.origin_documents.documents || []).map((item) => `<li><b>${escapeHtml(item.name)}</b> — ${escapeHtml(item.applicability)}${item.note ? ` <small>${escapeHtml(item.note)}</small>` : ""}</li>`).join("")}</ul><div class="result-caution">${escapeHtml((data.origin_documents.caveats || []).join(" "))}</div></section>` : ""}
      ${data.control_lookup ? `<section class="answer-section"><h3>Resmî kontrol tebliği Ek-1 eşleşmeleri</h3>${renderControlTool(data.control_lookup)}</section>` : ""}
      <section class="answer-section"><h3>Eksik veya teyit edilmesi gereken bilgiler</h3><ul class="missing-list">${(data.missing_information?.length ? data.missing_information : ["Kritik eksik alan bildirilmedi."]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>
      <section class="answer-section"><h3>TAREKS · TSE · kimyasal · laboratuvar kontrolleri</h3>${renderFindings(data.controls, sourceMap)}</section>
      <section class="answer-section"><h3>Gerekli belge ve izinler</h3>${renderFindings(data.required_documents, sourceMap)}</section>
      <section class="answer-section"><h3>Vergi ve mali yükümlülük bulguları</h3>${renderFindings(data.taxes, sourceMap, "tax")}</section>
      <section class="answer-section"><h3>Kullanıcı oranlarıyla maliyet taslağı</h3>${renderCost(data.deterministic_cost)}</section>
      ${data.image_observation ? `<section class="answer-section"><h3>Fotoğrafta görülenler</h3><p class="missing-list">${escapeHtml(data.image_observation)}</p></section>` : ""}
      ${renderExpertReviewPacket(data.expert_review_packet)}
      <section class="answer-section"><h3>Sonraki güvenli adımlar</h3><ol class="next-list">${(data.next_steps || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></section>
      <section class="answer-section"><h3>Resmî kanıt defteri · ${(data.sources || []).length} kaynak</h3><div class="source-ledger">${sources}</div></section>
      <div class="legal-banner"><strong>Önemli:</strong> ${escapeHtml(data.legal_notice)}</div>
      <div class="result-actions"><button class="consultant-send-result" id="sendResultToConsultant" type="button">Danışmana gönder</button><button id="saveScenario" type="button">Kanıt dosyasına kaydet</button><button id="printPrecheck" type="button">PDF olarak kaydet</button><button id="emailPrecheck" type="button">E-posta ile gönder</button></div>
    </article>
    <form class="followup-box" id="followupForm"><label class="field"><span>Bu ürün için takip sorusu</span><input id="followupQuestion" maxlength="1500" placeholder="Örn. TAREKS başvurusunda hangi teknik dosyalar hazırlanmalı?"></label><button class="analyse-button" type="submit"><span>Takip sorusunu sor</span><svg viewBox="0 0 24 24"><path d="m5 12 14 0M14 6l6 6-6 6"/></svg></button></form>`;
  $("#followupForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = $("#followupQuestion").value.trim();
    if (!value) return;
    $("#customsQuestion").value = value;
    $("#customsForm").requestSubmit();
  });
  $("#saveScenario")?.addEventListener("click", async () => {
    if (!state.auth?.authenticated) {
      showToast("Kanıt dosyası için Google hesabınızla giriş yapın.");
      window.setTimeout(() => { location.href = "/auth/google"; }, 700);
      return;
    }
    const button = $("#saveScenario"); button.disabled = true;
    try {
      await fetchJson("/api/dossiers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        title: data.inquiry?.product_description || $("#productDescription").value.trim() || "İthalat ön değerlendirmesi",
        product_name: $("#productDescription").value.trim(),
        gtip: data.inquiry?.candidate_gtip || $("#candidateGtip").value.trim(),
        origin_country: data.inquiry?.origin_country || $("#originCountry").value.trim(),
        effective_date: data.as_of || new Date().toISOString(), result: data,
      }) });
      showToast("Kanıt dosyası kaynak hash’leriyle sunucuya kaydedildi.");
      button.textContent = "Kanıt dosyasına kaydedildi";
      const auth = await fetchJson("/api/auth/me"); state.auth = auth;
    } catch (error) { showToast(error.message); button.disabled = false; }
  });
  $("#downloadExpertPacket")?.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(data.expert_review_packet, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `gumrukce-uzman-dosyasi-${data.inquiry?.candidate_gtip || "gtip-belirsiz"}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $("#sendResultToConsultant")?.addEventListener("click", () => {
    switchCustomsView("consultants");
    $("#consultantsPanelTitle")?.scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Bir danışman seçerek kontrollü dosya devrini başlatın.");
  });
}

function updateReadiness() {
  const tariffCode = $("#candidateGtip").value.replace(/\D/g, "");
  const checks = {
    vision: !state.customsImageData || state.customsVisionStatus === "confirmed",
    description: $("#productDescription").value.trim().length >= 12,
    origin: Boolean($("#originCountry").value.trim()),
    gtip: state.customsGtipSelectionConfirmed && [6, 8, 10, 12].includes(tariffCode.length),
    cost: ["#invoiceValue", "#freight", "#insurance"].every((selector) => $(selector).value !== ""),
    payment: Boolean($("#paymentMethod").value.trim() && $("#incoterm").value.trim()),
  };
  Object.entries(checks).forEach(([key, ready]) => {
    $(`[data-check="${key}"]`)?.classList.toggle("ready", ready);
  });
}

const visionFieldSelectors = [
  "#productDescription", "#composition", "#intendedUse", "#productCategory", "#brandModel",
  "#targetUser", "#declaredProductType",
  "#dimensions", "#labelText", "#dominantColors", "#constructionForm", "#componentsAccessories",
  "#functionMechanism", "#packaging", "#visibleFeatures", "#inferredFeatures",
  "#classificationQuestions", "#requiredUserInputs", "#productCondition",
];

function setVisionState(status, message, provider = "") {
  state.customsVisionStatus = status;
  const labels = {
    idle: "Bekliyor", ready: "Analize hazır", analysing: "Analiz ediliyor", review: "Kullanıcı kontrolü", confirmed: "Onaylandı", error: "Elle doldurun",
  };
  const panel = $("#attributeReview");
  if (panel) panel.hidden = !state.customsImageData || ["idle", "ready"].includes(status);
  const badge = $("#visionState");
  badge.dataset.state = status;
  badge.textContent = labels[status] || status;
  $("#visionMessage").textContent = message;
  $("#visionProvider").textContent = provider || "Model bilgisi analizden sonra gösterilir.";
  const confirm = $("#confirmAttributes");
  confirm.disabled = status === "analysing";
  confirm.querySelector("span").textContent = status === "confirmed"
    ? "Evsaflar onaylandı · Adayları yeniden bul"
    : "Evsafları onayla ve aday GTİP bul";
  updateVisionAnalyseButton(status);
  updateReadiness();
}

function updateVisionAnalyseButton(status) {
  const button = $("#analyseImageButton");
  const route = $("#visionRoute");
  if (!button || !route) return;
  const hasImage = Boolean(state.customsImageData);
  button.hidden = !hasImage;
  route.hidden = !hasImage;
  button.disabled = status === "analysing";
  button.setAttribute("aria-busy", status === "analysing" ? "true" : "false");
  const labels = {
    ready: "Ürünü Analiz Et",
    analysing: "Fotoğraf Analiz Ediliyor…",
    review: "Fotoğrafı Yeniden Analiz Et",
    confirmed: "Fotoğrafı Yeniden Analiz Et",
    error: "Analizi Tekrar Dene",
  };
  button.querySelector("span").textContent = labels[status] || "Ürünü Analiz Et";
}

function joinLines(values) {
  return Array.isArray(values) ? values.filter(Boolean).join("\n") : "";
}

function setVisionValue(selector, value, { preserveWhenEmpty = false } = {}) {
  const input = $(selector);
  if (!input || (preserveWhenEmpty && !value)) return;
  input.value = value || "";
  input.classList.toggle("vision-filled", Boolean(value));
}

function parseClassificationQuestions(value) {
  const seen = new Set();
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:[-•*]|\d+[.)])\s*/, "").trim())
    .filter((question) => {
      const key = question.toLocaleLowerCase("tr-TR");
      if (question.length < 3 || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 12);
}

function collectClassificationAnswers() {
  return parseClassificationQuestions($("#classificationQuestions").value).flatMap((question, index) => {
    const answer = $(`[data-classification-answer="${index}"]`)?.value?.trim()
      || state.customsClassificationAnswers[question]?.trim()
      || "";
    if (!answer) return [];
    return [{ question, answer }];
  });
}

function updateClassificationAnswerProgress() {
  const questions = parseClassificationQuestions($("#classificationQuestions").value);
  const answered = collectClassificationAnswers().length;
  $("#classificationAnswerProgress").textContent = `${answered} / ${questions.length} cevap`;
}

function renderClassificationAnswerFields({ clear = false } = {}) {
  const panel = $("#classificationAnswerPanel");
  const list = $("#classificationAnswerList");
  const questions = parseClassificationQuestions($("#classificationQuestions").value);
  if (clear) state.customsClassificationAnswers = {};
  panel.hidden = questions.length === 0;
  if (!questions.length) {
    list.replaceChildren();
    updateClassificationAnswerProgress();
    return;
  }
  list.innerHTML = questions.map((question, index) => `<label class="classification-answer-row">
    <span><b>${index + 1}</b>${escapeHtml(question)}</span>
    <textarea data-classification-answer="${index}" maxlength="1000" placeholder="Cevabınızı buraya yazın; kullanıcı istediği zaman düzeltebilir.">${escapeHtml(state.customsClassificationAnswers[question] || "")}</textarea>
  </label>`).join("");
  updateClassificationAnswerProgress();
}

function applyVisionAttributes(data) {
  const description = data.product_description || [data.product_name, data.product_category].filter(Boolean).join(" — ");
  setVisionValue("#productDescription", description);
  setVisionValue("#composition", data.composition);
  setVisionValue("#intendedUse", data.intended_use);
  setVisionValue("#productCategory", data.product_category);
  setVisionValue("#brandModel", [data.visible_brand, data.visible_model].filter(Boolean).join(" / "));
  setVisionValue("#dimensions", data.dimensions);
  setVisionValue("#labelText", data.label_text);
  setVisionValue("#dominantColors", joinLines(data.dominant_colors).replaceAll("\n", ", "));
  setVisionValue("#constructionForm", data.construction_form);
  setVisionValue("#componentsAccessories", joinLines(data.components_accessories));
  setVisionValue("#functionMechanism", data.function_mechanism);
  setVisionValue("#packaging", data.packaging);
  setVisionValue("#visibleFeatures", joinLines(data.visible_features));
  setVisionValue("#inferredFeatures", joinLines(data.inferred_features));
  setVisionValue("#classificationQuestions", joinLines(data.classification_questions));
  renderClassificationAnswerFields({ clear: true });
  setVisionValue("#requiredUserInputs", joinLines(data.required_user_inputs));
  setVisionValue("#originCountry", data.visible_origin_country, { preserveWhenEmpty: true });
  if (["new", "used"].includes(data.condition)) setVisionValue("#productCondition", data.condition);
  if (!$("#customsQuestion").value.trim()) {
    $("#customsQuestion").value = "Bu ürünün aday GTİP'i, ithalat vergileri, TAREKS/TSE kontrolleri, gerekli belgeleri ve ek maliyetleri nelerdir?";
  }
  const fileStatus = $("#productFileStatus");
  fileStatus.dataset.state = "filled";
  fileStatus.textContent = `${data.product_name || "Ürün"} evsafları ürün dosyasına eklendi. Alanları kontrol edip gerekiyorsa düzeltin.`;
  updateReadiness();
}

function classificationRequestBody() {
  return {
    product_description: $("#productDescription").value.trim(),
    product_category: $("#productCategory").value.trim(),
    composition: $("#composition").value.trim(),
    intended_use: $("#intendedUse").value.trim(),
    target_user: $("#targetUser").value.trim(),
    declared_product_type: $("#declaredProductType").value.trim(),
    construction_form: $("#constructionForm").value.trim(),
    function_mechanism: $("#functionMechanism").value.trim(),
    components_accessories: $("#componentsAccessories").value.trim(),
    label_text: $("#labelText").value.trim(),
    visible_features: $("#visibleFeatures").value.trim(),
    inferred_features: $("#inferredFeatures").value.trim(),
    classification_questions: $("#classificationQuestions").value.trim(),
    classification_answers: collectClassificationAnswers(),
    origin_country: $("#originCountry").value.trim(),
  };
}

function candidateRates(candidate) {
  if (candidate.rate_status === "origin_required") {
    return '<em>Vergi oranı için menşe ülke girin</em>';
  }
  if (candidate.rate_status === "ambiguous") {
    const customsVariants = candidate.rate_variants?.customs_duty || [];
    const additionalVariants = candidate.rate_variants?.additional_duty || [];
    const parts = [];
    if (customsVariants.length) parts.push(`GV ${customsVariants.map((rate) => `%${numberFormat.format(rate)}`).join("/")}`);
    if (additionalVariants.length) parts.push(`İGV ${additionalVariants.map((rate) => `%${numberFormat.format(rate)}`).join("/")}`);
    return `<em>${escapeHtml(parts.join(" · ") || "Oran alt GTİP’e göre değişiyor")} · alt kod seçilmeli</em>`;
  }
  const parts = [];
  if (candidate.customs_duty_rate != null) parts.push(`<b>GV %${escapeHtml(numberFormat.format(candidate.customs_duty_rate))}</b>`);
  if (candidate.additional_duty_rate != null) parts.push(`<b>İGV %${escapeHtml(numberFormat.format(candidate.additional_duty_rate))}</b>`);
  if (candidate.additional_financial_liability_rate != null) parts.push(`<b>EMY %${escapeHtml(numberFormat.format(candidate.additional_financial_liability_rate))}</b>`);
  return parts.join("") || '<em>Bu seviyede tek oran doğrulanamadı</em>';
}

function renderGtipSuggestions(data) {
  const panel = $("#gtipSuggestions");
  const list = $("#gtipSuggestionList");
  panel.hidden = false;
  $("#gtipSuggestionStatus").textContent = data.candidates?.length
    ? `${data.candidates.length} aday · ${data.model}`
    : "Aday bulunamadı";
  if (!data.candidates?.length) {
    list.innerHTML = `<div class="answer-error"><p>${escapeHtml(data.summary || "Aday kod üretilemedi.")}</p></div>`;
    return;
  }
  list.innerHTML = data.candidates.map((candidate, index) => {
    const evidence = candidate.classification_evidence || [];
    const references = evidence.flatMap((item) => item.regulation_references || []).slice(0, 3);
    const evidenceText = evidence.length
      ? `${evidence.length} resmî AB sınıflandırma sayfası · ${references.join(" · ") || "kod eşleşmesi"}`
      : "Bu aday için ürün-özel AB karar eşleşmesi bulunamadı";
    return `<button class="gtip-candidate-button${candidate.code === $("#candidateGtip").value.replace(/\D/g, "") && state.customsGtipSelectionConfirmed ? " selected" : ""}" type="button" data-candidate-index="${index}">
      <code>${escapeHtml(candidate.code)}<small>${escapeHtml(candidate.level)} · ${escapeHtml(candidate.confidence_score ?? 0)}/100 kanıt puanı · ${escapeHtml(candidate.model_votes ?? 1)} model oyu · ${escapeHtml(candidate.matched_gtip_count)} alt GTİP</small></code>
      <span>${escapeHtml(candidate.explanation)}<small class="gtip-candidate-evidence">${escapeHtml(evidenceText)}</small></span>
      <span class="gtip-candidate-rates">${candidateRates(candidate)}</span>
    </button>`;
  }).join("");
  $$('[data-candidate-index]').forEach((button) => button.addEventListener("click", async () => {
    const candidate = data.candidates[Number(button.dataset.candidateIndex)];
    state.customsSelectedCandidate = candidate;
    setSelectedTariffCode(candidate.code, { exact: candidate.code.length === 12 });
    $$('[data-candidate-index]').forEach((item) => item.classList.toggle("selected", item === button));
    showToast(`${candidate.code} seçildi; şimdi resmî Türk tarife alt dalları açılıyor.`);
    try {
      await loadTariffTree(candidate.code, candidate);
    } catch (error) {
      renderTariffTreeError(error.message || "Türk GTİP alt dalları getirilemedi.");
    }
  }));
}

function tariffLevelLabel(level) {
  return { HS6: "HS6", CN8: "CN8", TR10: "Türkiye 10", GTIP12: "GTİP12" }[level] || level || "Tarife";
}

function treeNodeRates(node) {
  if (node.rate_status === "origin_required") return "Menşe girildiğinde ortak oranlar doğrulanır";
  const safe = node.unambiguous_rates || {};
  const parts = [];
  if (safe.customs_duty != null) parts.push(`GV %${numberFormat.format(safe.customs_duty)}`);
  if (safe.additional_duty != null) parts.push(`İGV %${numberFormat.format(safe.additional_duty)}`);
  if (safe.additional_financial_liability != null) parts.push(`EMY %${numberFormat.format(safe.additional_financial_liability)}`);
  if (node.rate_status === "unambiguous" && parts.length) return `${parts.join(" · ")} · bütün alt satırlarda ortak`;
  const variants = Object.values(node.rate_variants || {}).flat();
  return variants.length ? `Alt satırlara göre değişiyor: ${[...new Set(variants)].map((rate) => `%${numberFormat.format(rate)}`).join(" / ")}` : "Bu dalda tek oran doğrulanamadı";
}

function setSelectedTariffCode(code, { exact = false } = {}) {
  const normalised = String(code || "").replace(/\D/g, "");
  state.customsApplyingTariffSelection = true;
  $("#candidateGtip").value = normalised;
  state.customsGtipSelectionConfirmed = [6, 8, 10, 12].includes(normalised.length);
  state.customsExactGtipConfirmed = exact && normalised.length === 12;
  state.customsAutoGtip = null;
  $("#candidateGtip").dispatchEvent(new Event("input", { bubbles: true }));
  state.customsApplyingTariffSelection = false;
  updateReadiness();
}

function tariffPathCodes(code) {
  const digits = String(code || "").replace(/\D/g, "");
  return [6, 8, 10, 12].filter((length) => length <= digits.length).map((length) => digits.slice(0, length));
}

function renderTariffTreeError(message) {
  const panel = $("#tariffTree");
  panel.hidden = false;
  $("#tariffTreeStatus").textContent = "Alt dallar alınamadı";
  $("#tariffTreeList").innerHTML = `<div class="answer-error"><p>${escapeHtml(message)}</p></div>`;
}

function renderTariffTree(tree, candidate = state.customsSelectedCandidate) {
  const panel = $("#tariffTree");
  const list = $("#tariffTreeList");
  const path = $("#tariffTreePath");
  const questions = $("#tariffTreeQuestions");
  panel.hidden = false;
  state.customsTariffTree = tree;
  path.innerHTML = tariffPathCodes(tree.prefix).map((code, index, values) => `<button type="button" data-tariff-path="${escapeHtml(code)}"${index === values.length - 1 ? ' aria-current="step"' : ""}>${escapeHtml(code)}</button>`).join('<span aria-hidden="true">›</span>');
  const decisionQuestions = [...new Set([
    ...(candidate?.decisive_missing_information || []),
    ...(state.customsClassificationResult?.missing_information || []),
  ].filter(Boolean))].slice(0, 8);
  questions.hidden = decisionQuestions.length === 0;
  questions.innerHTML = decisionQuestions.length
    ? `<b>Alt kodu seçmeden önce doğrulayın</b><ul>${decisionQuestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : "";

  if (tree.status !== "matched") {
    $("#tariffTreeStatus").textContent = "Resmî tarife eşleşmesi yok";
    list.innerHTML = '<div class="answer-error"><p>Bu kod aktif resmî tarife tablolarında doğrulanamadı.</p></div>';
  } else if (tree.exact_gtip_selected) {
    state.customsExactGtipConfirmed = true;
    state.customsGtipSelectionConfirmed = true;
    $("#tariffTreeStatus").textContent = "12 haneli satır doğrulandı";
    list.innerHTML = `<div class="tariff-tree-final"><b>${escapeHtml(tree.prefix)}</b><span>Aktif resmî tarife tablolarında bulunan GTİP12 satırı</span></div>`;
  } else {
    state.customsExactGtipConfirmed = false;
    $("#tariffTreeStatus").textContent = `${tree.total_children} ${tariffLevelLabel(tree.next_level)} dalı · kullanıcı seçimi gerekli`;
    list.innerHTML = tree.children.map((node) => `<button type="button" class="tariff-tree-node" data-tariff-child="${escapeHtml(node.code)}" data-tariff-final="${node.final ? "true" : "false"}">
      <code>${escapeHtml(node.code)}<small>${tariffLevelLabel(node.level)} · ${escapeHtml(node.descendant_count)} GTİP12 satırı</small></code>
      <span>${escapeHtml(treeNodeRates(node))}</span>
      <b>${node.final ? "Bu GTİP12’yi doğrula" : "Alt dalları aç"}</b>
    </button>`).join("");
  }
  $("#tariffTreeNotice").textContent = tree.exact_gtip_selected
    ? "Kodun resmî tabloda bulunması, ürünün bu kodda sınıflandırıldığını tek başına kanıtlamaz. Evsaf ve gerekçe kullanıcı tarafından doğrulanmıştır."
    : "Sistem alt dalı otomatik seçmez. 6/8/10 haneli kodlarda yalnız bütün alt satırlarda ortak olan oranlar güvenle gösterilebilir; TAREKS kapsamı için GTİP12 gerekir.";
  $$('[data-tariff-path]').forEach((button) => button.addEventListener("click", () => loadTariffTree(button.dataset.tariffPath, candidate).catch((error) => renderTariffTreeError(error.message))));
  $$('[data-tariff-child]').forEach((button) => button.addEventListener("click", async () => {
    const code = button.dataset.tariffChild;
    const exact = button.dataset.tariffFinal === "true";
    setSelectedTariffCode(code, { exact });
    if (exact) prefillVerifiedRates(code);
    await loadTariffTree(code, candidate).catch((error) => renderTariffTreeError(error.message));
    showToast(exact ? `${code} GTİP12 adayı kullanıcı seçimiyle doğrulandı.` : `${code} dalı seçildi; bir alt seviye açıldı.`);
  }));

async function prefillVerifiedRates(code) {
  const origin = $("#originCountry").value.trim();
  if (!origin) return;
  try {
    const tariff = await fetchJson("/api/tariff/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gtip: code, origin_country: origin }),
    });
    const safe = tariff.unambiguous_rates || {};
    let filled = 0;
    [["#customsDutyRate", safe.customs_duty], ["#additionalDutyRate", safe.additional_duty]].forEach(([selector, value]) => {
      const input = $(selector);
      if (value == null || !input || input.value.trim() !== "") return;
      input.value = String(value);
      input.classList.add("rate-suggested");
      input.title = "Resmî tarife satırından önerildi; onaylamadan veya düzeltmeden maliyet hesabı yapılmaz.";
      filled += 1;
    });
    if (filled) showToast("Vergi oranları resmî satırdan önerildi; doğrulayıp onaylayın.");
  } catch (error) { /* oran önerisi başarısız olsa da kod seçimi geçerli kalır */ }
}
  updateReadiness();
}

async function loadTariffTree(code, candidate = state.customsSelectedCandidate) {
  const panel = $("#tariffTree");
  panel.hidden = false;
  $("#tariffTreeStatus").textContent = "Resmî alt dallar hazırlanıyor…";
  $("#tariffTreeList").innerHTML = '<div class="analysis-loading"><i></i><div><b>Türk tarife ağacı taranıyor</b><span>Hiçbir alt kod otomatik seçilmiyor…</span></div></div>';
  const tree = await fetchJson("/api/tariff/tree", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gtip: code, origin_country: $("#originCountry").value.trim() }),
  });
  renderTariffTree(tree, candidate);
  return tree;
}

function resetGtipSuggestions({ clearAutoCode = false } = {}) {
  if (clearAutoCode && state.customsAutoGtip && $("#candidateGtip").value.replace(/\D/g, "") === state.customsAutoGtip) {
    $("#candidateGtip").value = "";
  }
  state.customsClassificationResult = null;
  state.customsAutoGtip = null;
  state.customsGtipSelectionConfirmed = false;
  state.customsExactGtipConfirmed = false;
  state.customsTariffTree = null;
  state.customsSelectedCandidate = null;
  $("#gtipSuggestions").hidden = true;
  $("#gtipSuggestionList").innerHTML = "";
  $("#gtipSuggestionStatus").textContent = "Evsaf onayından sonra hazırlanır.";
  $("#tariffTree").hidden = true;
  $("#tariffTreeList").innerHTML = "";
  $("#tariffTreePath").innerHTML = "";
  $("#tariffTreeQuestions").innerHTML = "";
  updateReadiness();
}

async function classifyApprovedProduct() {
  const panel = $("#gtipSuggestions");
  panel.hidden = false;
  $("#gtipSuggestionStatus").textContent = "Aday kodlar ve oranlar hazırlanıyor…";
  $("#gtipSuggestionList").innerHTML = '<div class="analysis-loading"><i></i><div><b>En yakın üç tarife aranıyor</b><span>Model adayları resmî tarife cetvelinde doğrulanıyor…</span></div></div>';
  const data = await fetchJson("/api/customs/classify-product", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(classificationRequestBody()),
  });
  state.customsClassificationResult = data;
  state.customsGtipSelectionConfirmed = false;
  state.customsExactGtipConfirmed = false;
  state.customsSelectedCandidate = null;
  $("#candidateGtip").value = "";
  $("#tariffTree").hidden = true;
  renderGtipSuggestions(data);
  return data;
}

async function refreshCandidateRates() {
  const data = state.customsClassificationResult;
  const origin = $("#originCountry").value.trim();
  if (!data?.candidates?.length || !origin) return;
  const updated = await Promise.all(data.candidates.map(async (candidate) => {
    const tariff = await fetchJson("/api/tariff/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gtip: candidate.code, origin_country: origin }),
    });
    const safe = tariff.unambiguous_rates || {};
    return {
      ...candidate,
      customs_duty_rate: safe.customs_duty ?? null,
      additional_duty_rate: safe.additional_duty ?? null,
      additional_financial_liability_rate: safe.additional_financial_liability ?? null,
      rate_variants: tariff.rate_variants || {},
      rate_status: tariff.ambiguous_measure_types?.length || safe.customs_duty == null ? "ambiguous" : "unambiguous",
    };
  }));
  state.customsClassificationResult = { ...data, candidates: updated };
  renderGtipSuggestions(state.customsClassificationResult);
}

async function analyseProductImage() {
  if (!state.customsImageData) return;
  setVisionState(
    "analysing",
    "Görsel yalnızca ürünün görünür evsaflarına çevriliyor. Bu aşamada GTİP, vergi veya TAREKS sorgusu yapılmaz.",
  );
  try {
    const data = await fetchJson("/api/customs/describe-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_data_url: state.customsImageData }),
    });
    state.customsVisionResult = data;
    applyVisionAttributes(data);
    setVisionState(
      "review",
      `${data.warning} Alanları düzeltin; araştırma ancak onayınızdan sonra başlar.`,
      `Görsel model: ${data.provider} · ${data.model} · güven: ${data.confidence}`,
    );
    $("#productFileStatus").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    state.customsVisionResult = null;
    $("#productFileStatus").dataset.state = "error";
    $("#productFileStatus").textContent = "Görsel analizi ürün dosyasına işlenemedi. Analizi tekrar deneyin veya alanları elle doldurun.";
    setVisionState(
      "error",
      `${error.message || "Görsel analizi tamamlanamadı."} Ürün evsaflarını elle doldurup yine de açıkça onaylayabilirsiniz.`,
    );
  }
}

async function setProductImage(file) {
  const allowed = ["image/jpeg", "image/png", "image/webp"];
  if (!file) {
    state.customsImageData = null;
    state.customsVisionResult = null;
    state.customsClassificationAnswers = {};
    renderClassificationAnswerFields({ clear: true });
    state.customsVisionStatus = "idle";
    resetGtipSuggestions({ clearAutoCode: true });
    $("#imagePreview").hidden = true;
    $("#uploadZone").classList.remove("has-image");
    $("#attributeReview").hidden = true;
    $("#uploadTitle").textContent = "Ürün fotoğrafı ekle";
    $("#uploadHint").textContent = "JPEG, PNG veya WebP · en az 80×80 piksel · en fazla 8 MB";
    $("#productFileStatus").dataset.state = "waiting";
    $("#productFileStatus").textContent = "Görsel analizi tamamlandığında temel evsaflar önce bu ürün dosyasına işlenir.";
    updateVisionAnalyseButton("idle");
    updateReadiness();
    return;
  }
  if (!allowed.includes(file.type) || file.size > 8 * 1024 * 1024) {
    $("#productImage").value = "";
    showToast("JPEG, PNG veya WebP biçiminde en fazla 8 MB görsel yükleyin.");
    return;
  }
  state.customsImageData = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  $("#imagePreview").src = state.customsImageData;
  $("#imagePreview").hidden = false;
  $("#uploadZone").classList.add("has-image");
  $("#uploadTitle").textContent = file.name;
  $("#uploadHint").textContent = `${numberFormat.format(Math.ceil(file.size / 1024))} KB · analiz siz başlatmadan gönderilmez`;
  state.customsVisionResult = null;
  state.customsClassificationAnswers = {};
  renderClassificationAnswerFields({ clear: true });
  resetGtipSuggestions({ clearAutoCode: true });
  $("#productFileStatus").dataset.state = "waiting";
  $("#productFileStatus").textContent = "Fotoğraf hazır. Analiz sonucu önce bu ürün dosyasına işlenecek.";
  setVisionState(
    "ready",
    "Fotoğraf hazır. Ürünü Analiz Et düğmesine bastığınızda yalnızca görünür evsaflar çıkarılır.",
  );
}

function customsRequestBody() {
  return {
    question: $("#customsQuestion").value.trim(),
    product_description: $("#productDescription").value.trim(),
    candidate_gtip: $("#candidateGtip").value.trim() || null,
    tariff_selection_confirmed: state.customsGtipSelectionConfirmed,
    exact_gtip_confirmed: state.customsExactGtipConfirmed,
    classification_verification_status: state.customsClassificationResult?.verification_status || null,
    classification_confidence_score: state.customsSelectedCandidate?.confidence_score ?? null,
    classification_models: (state.customsClassificationResult?.models || []).slice(0, 3),
    origin_country: $("#originCountry").value.trim() || null,
    dispatch_country: $("#dispatchCountry").value.trim() || null,
    intended_use: $("#intendedUse").value.trim() || null,
    target_user: $("#targetUser").value.trim() || null,
    declared_product_type: $("#declaredProductType").value.trim() || null,
    composition: $("#composition").value.trim() || null,
    product_category: $("#productCategory").value.trim() || null,
    brand_model: $("#brandModel").value.trim() || null,
    dimensions: $("#dimensions").value.trim() || null,
    label_text: $("#labelText").value.trim() || null,
    dominant_colors: $("#dominantColors").value.trim() || null,
    construction_form: $("#constructionForm").value.trim() || null,
    components_accessories: $("#componentsAccessories").value.trim() || null,
    function_mechanism: $("#functionMechanism").value.trim() || null,
    packaging: $("#packaging").value.trim() || null,
    visible_features: $("#visibleFeatures").value.trim() || null,
    inferred_features: $("#inferredFeatures").value.trim() || null,
    classification_questions: $("#classificationQuestions").value.trim() || null,
    classification_answers: collectClassificationAnswers(),
    required_user_inputs: $("#requiredUserInputs").value.trim() || null,
    condition: $("#productCondition").value,
    invoice_value: nullableNumber("#invoiceValue"),
    freight: nullableNumber("#freight"),
    insurance: nullableNumber("#insurance"),
    other_pre_import_costs: nullableNumber("#otherCosts"),
    quantity: nullableNumber("#quantity"),
    currency: $("#currency").value,
    incoterm: $("#incoterm").value.trim() || null,
    payment_method: $("#paymentMethod").value.trim() || null,
    customs_duty_rate: nullableNumber("#customsDutyRate"),
    additional_duty_rate: nullableNumber("#additionalDutyRate"),
    additional_financial_liability_rate: nullableNumber("#additionalFinancialLiabilityRate"),
    anti_dumping_amount: nullableNumber("#antiDumpingAmount"),
    kkdf_rate: nullableNumber("#kkdfRate"),
    vat_rate: nullableNumber("#vatRate"),
    sct_amount: nullableNumber("#sctAmount"),
    surveillance_unit_value: nullableNumber("#surveillanceUnitValue"),
    has_surveillance_certificate: $("#hasSurveillanceCertificate").value === "" ? null : $("#hasSurveillanceCertificate").value === "true",
  };
}

$("#productImage").addEventListener("change", (event) => setProductImage(event.target.files?.[0]).catch(() => showToast("Görsel okunamadı.")));
$("#analyseImageButton").addEventListener("click", analyseProductImage);
const uploadZone = $("#uploadZone");
["dragenter", "dragover"].forEach((name) => uploadZone.addEventListener(name, (event) => { event.preventDefault(); uploadZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((name) => uploadZone.addEventListener(name, (event) => { event.preventDefault(); uploadZone.classList.remove("dragging"); }));
uploadZone.addEventListener("drop", (event) => setProductImage(event.dataTransfer.files?.[0]).catch(() => showToast("Görsel okunamadı.")));
$$('#customsForm input, #customsForm textarea, #customsForm select').forEach((input) => input.addEventListener("input", updateReadiness));
visionFieldSelectors.forEach((selector) => $(selector)?.addEventListener("input", () => {
  if (state.customsImageData && state.customsVisionStatus === "confirmed") {
    resetGtipSuggestions({ clearAutoCode: true });
    setVisionState(
      "review",
      "Onaydan sonra evsaf değişti. Güncel alanları yeniden onaylamadan resmî araştırma başlatılamaz.",
      state.customsVisionResult ? `Görsel model: ${state.customsVisionResult.provider} · ${state.customsVisionResult.model}` : "Elle düzenlenen evsaf",
    );
  }
}));

$("#classificationQuestions").addEventListener("input", () => renderClassificationAnswerFields());
$("#classificationAnswerList").addEventListener("input", (event) => {
  const input = event.target.closest("[data-classification-answer]");
  if (!input) return;
  const questions = parseClassificationQuestions($("#classificationQuestions").value);
  const question = questions[Number(input.dataset.classificationAnswer)];
  if (question) state.customsClassificationAnswers[question] = input.value;
  updateClassificationAnswerProgress();
  updateReadiness();
  if (state.customsImageData && state.customsVisionStatus === "confirmed") {
    resetGtipSuggestions({ clearAutoCode: true });
    setVisionState("review", "Eksik bilgi cevabı değişti. Güncel cevaplarla aday GTİP'i yeniden bulun.", "Kullanıcı tarafından tamamlanan evsaf");
  }
});
$("#goToCostFields").addEventListener("click", () => {
  $("#shipmentDetails").open = true;
  $("#costDetails").open = true;
  $("#costDetails").scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => $("#invoiceValue").focus({ preventScroll: true }), 450);
});

let originRateTimer = null;
$("#originCountry").addEventListener("input", () => {
  window.clearTimeout(originRateTimer);
  if (!state.customsClassificationResult?.candidates?.length) return;
  if (!$("#originCountry").value.trim()) {
    state.customsClassificationResult.candidates = state.customsClassificationResult.candidates.map((candidate) => ({
      ...candidate,
      customs_duty_rate: null,
      additional_duty_rate: null,
      additional_financial_liability_rate: null,
      rate_status: "origin_required",
    }));
    renderGtipSuggestions(state.customsClassificationResult);
    return;
  }
  const selectedCode = $("#candidateGtip").value.replace(/\D/g, "");
  originRateTimer = window.setTimeout(async () => {
    try {
      await refreshCandidateRates();
      if (state.customsGtipSelectionConfirmed && [6, 8, 10, 12].includes(selectedCode.length)) {
        await loadTariffTree(selectedCode);
      }
    } catch (error) {
      showToast(error.message || "Aday oranları yenilenemedi.");
    }
  }, 650);
});

let manualTariffTimer = null;
$("#candidateGtip").addEventListener("input", () => {
  const current = $("#candidateGtip").value.replace(/\D/g, "");
  if (state.customsAutoGtip && current !== state.customsAutoGtip) state.customsAutoGtip = null;
  if (!state.customsApplyingTariffSelection) {
    state.customsGtipSelectionConfirmed = false;
    state.customsExactGtipConfirmed = false;
    state.customsSelectedCandidate = state.customsClassificationResult?.candidates?.find((candidate) => candidate.code === current) || null;
    window.clearTimeout(manualTariffTimer);
    if ([6, 8, 10, 12].includes(current.length)) {
      manualTariffTimer = window.setTimeout(async () => {
        try {
          const tree = await loadTariffTree(current, state.customsSelectedCandidate);
          if (tree.status === "matched") {
            state.customsGtipSelectionConfirmed = true;
            state.customsExactGtipConfirmed = tree.exact_gtip_selected;
            updateReadiness();
            if (state.customsPendingSubmit) {
              state.customsPendingSubmit = false;
              showToast(`${current} doğrulandı; analiz başlatılıyor.`);
              $("#customsForm").requestSubmit();
            } else {
              showToast(`${current} aktif resmî tarife ağacında doğrulandı.`);
            }
          } else if (state.customsPendingSubmit) {
            state.customsPendingSubmit = false;
            showToast("Kod resmî tarife ağacında bulunamadı; analiz başlatılmadı.");
          }
        } catch (error) {
          state.customsPendingSubmit = false;
          renderTariffTreeError(error.message || "Elle girilen kod doğrulanamadı.");
        }
      }, 650);
    } else {
      $("#tariffTree").hidden = true;
    }
  }
  $$('[data-candidate-index]').forEach((button) => {
    const candidate = state.customsClassificationResult?.candidates?.[Number(button.dataset.candidateIndex)];
    button.classList.toggle("selected", state.customsGtipSelectionConfirmed && candidate?.code === current);
  });
  updateReadiness();
});

$("#confirmAttributes").addEventListener("click", async () => {
  if (state.customsVisionStatus === "analysing") return;
  if ($("#productDescription").value.trim().length < 12) {
    showToast("Onaylamadan önce teknik ürün tanımını tamamlayın.");
    $("#productDescription").focus();
    return;
  }
  setVisionState(
    "confirmed",
    "Evsaflar onaylandı. En yakın üç HS/CN adayı resmî tarife cetvelinde doğrulanıyor.",
    state.customsVisionResult
      ? `Görsel model: ${state.customsVisionResult.provider} · ${state.customsVisionResult.model} · kullanıcı onaylı`
      : "Elle girilen evsaf · kullanıcı onaylı",
  );
  const confirm = $("#confirmAttributes");
  confirm.disabled = true;
  confirm.querySelector("span").textContent = "Aday GTİP’ler bulunuyor…";
  try {
    const classification = await classifyApprovedProduct();
    if (classification.candidates?.length) {
      setVisionState(
        "confirmed",
        `${classification.candidates.length} aday kod bulundu. Sistem hiçbirini otomatik seçmedi; bir adayı seçerek Türk GTİP12 alt dallarını açın.`,
        state.customsVisionResult
          ? `Görsel model: ${state.customsVisionResult.provider} · ${state.customsVisionResult.model} · sınıflandırma: ${classification.model}`
          : `Sınıflandırma modeli: ${classification.model}`,
      );
      showToast(`${classification.candidates.length} aday tarife kodu bulundu.`);
      $("#gtipSuggestions").scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      setVisionState("confirmed", classification.summary, `Sınıflandırma modeli: ${classification.model}`);
      showToast("Aday kod için ürün evsafı yetersiz kaldı.");
    }
  } catch (error) {
    $("#gtipSuggestions").hidden = false;
    $("#gtipSuggestionStatus").textContent = "Adaylar alınamadı";
    $("#gtipSuggestionList").innerHTML = `<div class="answer-error"><p>${escapeHtml(error.message || "Aday kodlar üretilemedi.")}</p></div>`;
    setVisionState("confirmed", "Evsaflar onaylandı ancak aday GTİP üretilemedi. Tekrar deneyebilir veya kodu elle girebilirsiniz.");
  } finally {
    confirm.disabled = false;
  }
});

$("#customsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.customsImageData && state.customsVisionStatus !== "confirmed") {
    if (["idle", "ready"].includes(state.customsVisionStatus)) {
      showToast("Önce Ürünü Analiz Et düğmesine basın.");
      $("#analyseImageButton").scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      showToast("Önce fotoğraftan çıkarılan evsafları kontrol edip onaylayın.");
      $("#attributeReview").scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return;
  }
  const selectedTariffCode = $("#candidateGtip").value.replace(/\D/g, "");
  if (state.customsClassificationResult?.candidates?.length && !state.customsGtipSelectionConfirmed) {
    showToast("Önce bir tarife adayını veya doğrulanmış alt dalı seçin.");
    $("#gtipSuggestions").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  if (selectedTariffCode && ![6, 8, 10, 12].includes(selectedTariffCode.length)) {
    showToast("Tarife kodu 6, 8, 10 veya 12 haneli olmalıdır.");
    $("#candidateGtip").focus();
    return;
  }
  if (selectedTariffCode && !state.customsGtipSelectionConfirmed) {
    state.customsPendingSubmit = true;
    showToast("Kod resmî tarife ağacında doğrulanıyor; analiz doğrulama biter bitmez kendiliğinden başlayacak.");
    return;
  }
  state.customsPendingSubmit = false;
  if (selectedTariffCode && selectedTariffCode.length < 12) {
    showToast("Üst tarife koduyla yalnız ortak oranlar gösterilir; TAREKS kapsamı GTİP12 seçilmeden kesinleşmez.");
  }
  const button = $("#analyseButton");
  const result = $("#customsResult");
  const loading = $("#analysisLoading");
  result.hidden = false;
  loading.hidden = false;
  $("#customsOutput").innerHTML = "";
  button.disabled = true;
  button.querySelector("span").textContent = "Resmî kaynaklar taranıyor…";
  result.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const data = await fetchJson("/api/customs/precheck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(customsRequestBody()),
    });
    renderCustomsResult(data);
  } catch (error) {
    $("#customsOutput").innerHTML = `<div class="answer-error"><h2>Ön değerlendirme tamamlanamadı</h2><p>${escapeHtml(error.message || "Lütfen daha sonra yeniden deneyin.")}</p></div>`;
  } finally {
    loading.hidden = true;
    button.disabled = false;
    button.querySelector("span").textContent = "GTİP bul · vergi ve TAREKS'i araştır";
  }
});

function formatUnixDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(Number(value) * 1000));
}

const consultationStatusLabels = {
  sent: "Yanıt bekliyor", accepted: "Danışman kabul etti", declined: "Danışman kabul etmedi", closed: "Görüşme kapandı",
};

function consultantCard(item) {
  const canSend = Boolean(state.currentCustomsResult);
  return `<article class="consultant-card">
    <header><span class="consultant-monogram">${escapeHtml((item.display_name || "D").slice(0, 1).toUpperCase())}</span><div><h3>${escapeHtml(item.display_name)}</h3><p>${escapeHtml(item.title)}</p></div><b>ONAYLI PROFİL</b></header>
    <p class="consultant-bio-text">${escapeHtml(item.bio)}</p>
    <div class="consultant-meta"><span>${escapeHtml(item.city || "Konum belirtilmedi")}</span><span>${item.service_mode === "hybrid" ? "Çevrim içi + yüz yüze" : "Çevrim içi"}</span><span>${escapeHtml(item.experience_years)} yıl deneyim</span></div>
    <ul>${(item.expertise || []).map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>
    <footer><small>Mevzuat danışmanlığı · fiilî gümrük işlemi değildir</small><button type="button" data-send-consultant="${escapeHtml(item.id)}" ${canSend ? "" : "disabled"}>${canSend ? "Analiz dosyasını gönder" : "Önce ürün analizi oluştur"}</button></footer>
  </article>`;
}

async function loadConsultants() {
  const target = $("#consultantGrid");
  target.innerHTML = "<p>Danışmanlar yükleniyor…</p>";
  try {
    const publicData = await fetchJson("/api/consultants");
    state.consultants = publicData.items || [];
    const marketplaceEnabled = publicData.enabled !== false;
    state.consultantsMarketplace = marketplaceEnabled;
    document.body.classList.toggle("marketplace-enabled", marketplaceEnabled);
    target.innerHTML = publicData.items.length
      ? publicData.items.map(consultantCard).join("")
      : '<div class="consultant-empty"><b>İlk danışman başvuruları bekleniyor</b><p>Ücretsiz başvuru yapabilir; yönetici incelemesinden sonra bu dizinde yer alabilirsiniz.</p></div>';
    if (state.auth?.authenticated) {
      const [profileData] = await Promise.all([
        fetchJson("/api/consultants/me"), loadConsultationRequests(),
      ]);
      if (profileData.profile) fillConsultantApplication(profileData.profile);
    } else {
      $("#consultationRequestList").innerHTML = '<p class="consultant-login-note">Taleplerinizi görmek veya danışman olmak için <a href="/auth/google">Google ile giriş yapın</a>.</p>';
    }
  } catch (error) {
    target.innerHTML = `<div class="answer-error"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function fillConsultantApplication(profile) {
  $("#consultantName").value = profile.display_name || "";
  $("#consultantTitle").value = profile.title || "";
  $("#consultantCity").value = profile.city || "";
  $("#consultantMode").value = profile.service_mode || "online";
  $("#consultantExperience").value = profile.experience_years ?? 0;
  $("#consultantBio").value = profile.bio || "";
  $$('[name="consultantExpertise"]').forEach((input) => { input.checked = (profile.expertise || []).includes(input.value); });
  const labels = { pending: "Başvurunuz yönetici incelemesinde.", active: "Profiliniz yayında. Değişiklik yaparsanız yeniden incelemeye alınır.", suspended: "Profiliniz yayında değil; yönetici incelemesi gerekiyor." };
  $("#consultantApplicationStatus").textContent = labels[profile.status] || "";
  $("#consultantApplicationStatus").dataset.status = profile.status || "pending";
}

function requestCard(item) {
  const packet = item.packet || {};
  const party = item.direction === "incoming" ? "Başvuru sahibi" : item.consultant_name;
  const sourceLinks = (packet.official_source_urls || []).slice(0, 12).map((url, index) => `<a href="${safeUrl(url)}" target="_blank" rel="noreferrer">Resmî kaynak ${index + 1} ↗</a>`).join("");
  const messages = (item.messages || []).map((message) => `<div class="consultation-message${message.mine ? " mine" : ""}"><b>${message.mine ? "Siz" : "Karşı taraf"}</b><p>${escapeHtml(message.body)}</p><time>${escapeHtml(formatUnixDate(message.created_at))}</time></div>`).join("");
  const mayReply = item.status === "accepted";
  const statusActions = item.direction === "incoming" && item.status === "sent"
    ? `<button type="button" data-request-status="accepted">Talebi kabul et</button><button type="button" data-request-status="declined" class="decline">Kabul etme</button>`
    : !["declined", "closed"].includes(item.status) ? '<button type="button" data-request-status="closed" class="decline">Görüşmeyi kapat</button>' : "";
  return `<details class="consultation-request" data-request-id="${escapeHtml(item.id)}">
    <summary><div><span>${item.direction === "incoming" ? "GELEN" : "GÖNDERİLEN"}</span><b>${escapeHtml(item.subject)}</b><small>${escapeHtml(party || "Kullanıcı")} · ${escapeHtml(formatUnixDate(item.created_at))}</small></div><em data-status="${escapeHtml(item.status)}">${escapeHtml(consultationStatusLabels[item.status] || item.status)}</em></summary>
    <div class="consultation-request-body"><p class="initial-message">${escapeHtml(item.message)}</p>
      <div class="shared-packet"><b>Paylaşılan analiz özeti</b><p>${escapeHtml(packet.summary || "Özet bulunmuyor.")}</p><code>${escapeHtml(packet.inquiry?.candidate_gtip || "GTİP belirsiz")}</code><span>${escapeHtml(packet.inquiry?.origin_country || "Menşe belirtilmedi")}</span><nav>${sourceLinks || "Resmî kaynak URL’si bulunmuyor."}</nav></div>
      <div class="consultation-thread">${messages || "<p>Henüz ek mesaj yok.</p>"}</div>
      ${mayReply ? `<form class="consultation-reply"><label class="field"><span>Görüşme mesajı</span><textarea required minlength="2" maxlength="2000" placeholder="Yanıtınızı veya ek sorunuzu yazın."></textarea></label><button type="submit">Mesajı gönder</button></form>` : item.status === "sent" ? '<p class="reply-lock">Mesajlaşma, danışman talebi kabul ettikten sonra açılır.</p>' : ""}
      <div class="consultation-status-actions">${statusActions}</div>
    </div>
  </details>`;
}

function consultationAttentionCount(data) {
  const needsMe = (item) => {
    if (item.direction === "incoming" && item.status === "sent") return true;
    if (item.status !== "accepted") return false;
    const last = (item.messages || []).at(-1);
    return Boolean(last && !last.mine);
  };
  return [...(data.incoming || []), ...(data.outgoing || [])].filter(needsMe).length;
}

function renderConsultationBadge(count) {
  state.consultationBadge = count;
  const tab = $('[data-customs-view="consultants"]');
  if (!tab) return;
  let badge = tab.querySelector(".tab-badge");
  if (!count) { badge?.remove(); return; }
  if (!badge) { badge = document.createElement("i"); badge.className = "tab-badge"; tab.append(badge); }
  badge.textContent = String(count);
  badge.setAttribute("aria-label", `${count} bekleyen danışmanlık talebi`);
}

async function refreshConsultationBadge() {
  if (!state.auth?.authenticated) return renderConsultationBadge(0);
  try { renderConsultationBadge(consultationAttentionCount(await fetchJson("/api/consultation-requests"))); }
  catch { /* rozet bilgilendirme amaçlıdır */ }
}

async function loadConsultationRequests() {
  const target = $("#consultationRequestList");
  if (!state.auth?.authenticated) return;
  target.innerHTML = "<p>Danışmanlık talepleri yükleniyor…</p>";
  try {
    const data = await fetchJson("/api/consultation-requests");
    renderConsultationBadge(consultationAttentionCount(data));
    const items = [...(data.incoming || []), ...(data.outgoing || [])];
    target.innerHTML = items.length ? items.map(requestCard).join("") : "<p>Henüz danışmanlık talebiniz yok.</p>";
  } catch (error) { target.innerHTML = `<div class="answer-error"><p>${escapeHtml(error.message)}</p></div>`; }
}

function openConsultationDialog(consultant) {
  if (!state.auth?.authenticated) {
    showToast("Danışmana dosya göndermek için Google hesabınızla giriş yapın.");
    window.setTimeout(() => { location.href = "/auth/google"; }, 700);
    return;
  }
  if (!state.currentCustomsResult) return showToast("Önce Ürüne Sor alanında bir analiz oluşturun.");
  state.selectedConsultant = consultant;
  $("#consultationAdvisorName").textContent = `${consultant.display_name} · ${consultant.title}`;
  const inquiry = state.currentCustomsResult.inquiry || {};
  $("#consultationSubject").value = `${inquiry.candidate_gtip || "GTİP"} için sınıflandırma ve mevzuat görüşü`;
  $("#consultationMessage").value = "Analizdeki aday GTİP, ticaret önlemleri ve ürün güvenliği kapsamını resmî kaynaklarıyla değerlendirmenizi rica ederim.";
  $("#consultationConsent").checked = false;
  $("#consultationDialog").showModal();
}

function switchCustomsView(view) {
  $$('[data-customs-view]').forEach((button) => button.classList.toggle("active", button.dataset.customsView === view));
  $$('[data-customs-panel]').forEach((panel) => { panel.hidden = panel.dataset.customsPanel !== view; });
  if (view === "changes") {
    renderWatchList();
    loadChanges();
  }
  if (view === "consultants") loadConsultants();
}

$$('[data-customs-view]').forEach((button) => button.addEventListener("click", () => switchCustomsView(button.dataset.customsView)));

$("#refreshConsultants").addEventListener("click", loadConsultants);
$("#refreshConsultationRequests").addEventListener("click", () => {
  if (!state.auth?.authenticated) return showToast("Talepler için Google hesabınızla giriş yapın.");
  loadConsultationRequests();
});
$("#openConsultantApplication").addEventListener("click", () => {
  if (!state.auth?.authenticated) {
    showToast("Ücretsiz danışman kaydı için Google hesabınızla giriş yapın.");
    window.setTimeout(() => { location.href = "/auth/google"; }, 700);
    return;
  }
  $("#consultantApplication").open = true;
  $("#consultantApplication").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("#consultantGrid").addEventListener("click", (event) => {
  const button = event.target.closest("[data-send-consultant]");
  if (!button || button.disabled) return;
  const consultant = state.consultants.find((item) => item.id === button.dataset.sendConsultant);
  if (consultant) openConsultationDialog(consultant);
});
$("#consultantApplicationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.auth?.authenticated) return showToast("Başvuru için Google hesabınızla giriş yapın.");
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const data = await fetchJson("/api/consultants/me", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        display_name: $("#consultantName").value.trim(), title: $("#consultantTitle").value,
        city: $("#consultantCity").value.trim(), service_mode: $("#consultantMode").value,
        experience_years: Number($("#consultantExperience").value || 0),
        bio: $("#consultantBio").value.trim(),
        expertise: $$('[name="consultantExpertise"]:checked').map((input) => input.value),
        advisory_only_accepted: $("#consultantTerms").checked,
      }),
    });
    fillConsultantApplication(data.profile);
    showToast("Ücretsiz danışman başvurunuz incelemeye gönderildi.");
  } catch (error) { showToast(error.message); }
  finally { button.disabled = false; }
});

function updateFieldCounter(input) {
  const hint = document.querySelector(`[data-counter-for="${input.id}"]`);
  if (!hint) return;
  const length = input.value.trim().length;
  const min = Number(input.getAttribute("minlength") || 0);
  const max = Number(input.getAttribute("maxlength") || 0);
  const short = length < min;
  hint.textContent = short ? `${length} / ${max} · en az ${min} karakter${length ? ` (${min - length} daha)` : ""}` : `${length} / ${max}`;
  hint.classList.toggle("short", short && length > 0);
}
["#consultationSubject", "#consultationMessage"].forEach((selector) => {
  const input = $(selector);
  if (!input) return;
  input.addEventListener("input", () => updateFieldCounter(input));
  updateFieldCounter(input);
});
$("#consultationForm button[type=submit]")?.addEventListener("click", (event) => {
  const form = $("#consultationForm");
  if (form.checkValidity()) return;
  event.preventDefault();
  const invalid = form.querySelector(":invalid");
  const label = invalid?.closest("label")?.querySelector("span")?.textContent?.replace("*", "").trim() || "Form";
  const min = invalid?.getAttribute("minlength");
  showToast(invalid?.type === "checkbox" ? "Paylaşım onayı kutusunu işaretleyin." : min ? `${label}: en az ${min} karakter yazın.` : `${label} alanı zorunludur.`);
  invalid?.focus();
  form.reportValidity();
});

function closeConsultationDialog() { $("#consultationDialog").close(); state.selectedConsultant = null; }
$("#closeConsultationDialog").addEventListener("click", closeConsultationDialog);
$("#cancelConsultation").addEventListener("click", closeConsultationDialog);
$("#consultationDialog").addEventListener("click", (event) => { if (event.target === $("#consultationDialog")) closeConsultationDialog(); });
$("#consultationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const consultant = state.selectedConsultant;
  if (!consultant || !state.currentCustomsResult) return showToast("Danışman veya analiz dosyası bulunamadı.");
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await fetchJson("/api/consultation-requests", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        consultant_id: consultant.id, subject: $("#consultationSubject").value.trim(),
        message: $("#consultationMessage").value.trim(), share_consent: $("#consultationConsent").checked,
        result: state.currentCustomsResult,
      }),
    });
    closeConsultationDialog();
    await loadConsultationRequests();
    $("#consultationInbox").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Analiz özeti danışmana güvenle gönderildi.");
  } catch (error) { showToast(error.message); }
  finally { button.disabled = false; }
});

$("#consultationRequestList").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-request-status]");
  if (!button) return;
  const requestNode = button.closest("[data-request-id]");
  button.disabled = true;
  try {
    await fetchJson(`/api/consultation-requests/${encodeURIComponent(requestNode.dataset.requestId)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: button.dataset.requestStatus }),
    });
    await loadConsultationRequests();
    showToast("Danışmanlık talebi güncellendi.");
  } catch (error) { showToast(error.message); button.disabled = false; }
});
$("#consultationRequestList").addEventListener("submit", async (event) => {
  const form = event.target.closest(".consultation-reply");
  if (!form) return;
  event.preventDefault();
  const requestNode = form.closest("[data-request-id]");
  const textarea = form.querySelector("textarea");
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await fetchJson(`/api/consultation-requests/${encodeURIComponent(requestNode.dataset.requestId)}/messages`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body: textarea.value.trim() }),
    });
    await loadConsultationRequests();
    showToast("Mesaj görüşmeye eklendi.");
  } catch (error) { showToast(error.message); button.disabled = false; }
});

function tariffRows(items) {
  if (!items?.length) return '<tr><td colspan="5">Bu menşe sütunu için uygulanabilir satır bulunamadı.</td></tr>';
  return items.map((item) => `<tr>
    <td><code>${escapeHtml(item.gtip)}</code><br>${escapeHtml(item.measure_type)}</td>
    <td>${item.rate == null ? escapeHtml(item.rate_text) : `%${escapeHtml(item.rate)}`}${item.footnote ? `<br><small>Dipnot: ${escapeHtml(item.footnote)}</small>` : ""}</td>
    <td>${escapeHtml(item.country_group)} · ${escapeHtml(item.country_group_description)}</td>
    <td>${escapeHtml(item.source_file)}<br>${escapeHtml(item.source_sheet)} · satır ${escapeHtml(item.source_row)}</td>
    <td><a href="${safeUrl(item.source_url)}" target="_blank" rel="noreferrer">Resmî kaynak ↗</a><br><small>SHA ${escapeHtml(item.archive_sha256.slice(0, 12))}</small></td>
  </tr>`).join("");
}

const tariffMeasureLabels = {
  customs_duty: "Gümrük vergisi",
  additional_duty: "İlave gümrük vergisi",
  additional_financial_liability: "Ek mali yükümlülük",
};

function tariffMatchSummary(tariff) {
  if (tariff.match_mode !== "prefix") return "";
  const variants = Object.entries(tariff.rate_variants || {}).map(([type, rates]) => {
    const label = tariffMeasureLabels[type] || type;
    const values = rates?.length ? rates.map((rate) => `%${numberFormat.format(rate)}`).join(" / ") : "oran okunamadı";
    const ambiguous = (tariff.ambiguous_measure_types || []).includes(type);
    return `<li><b>${escapeHtml(label)}:</b> ${escapeHtml(values)}${ambiguous ? " · oran veya kapsam alt GTİP’e göre değişiyor" : " · bütün alt satırlarda aynı"}</li>`;
  }).join("");
  return `<div class="result-caution"><strong>${escapeHtml(tariff.gtip.length)} haneli kodla ön ek araması:</strong> ${escapeHtml(tariff.matched_gtip_count || 0)} adet 12 haneli Türk GTİP satırı bulundu.${variants ? `<ul>${variants}</ul>` : ""}</div>`;
}

const rateFieldByMeasure = {
  customs_duty: "#customsDutyRate",
  additional_duty: "#additionalDutyRate",
  additional_financial_liability: "#additionalFinancialLiabilityRate",
};

function applicableTariffRates(tariff) {
  if (!tariff) return {};
  const ambiguous = new Set(tariff.ambiguous_measure_types || []);
  const rates = {};
  (tariff.measures || []).forEach((item) => {
    if (item.rate == null || !rateFieldByMeasure[item.measure_type] || ambiguous.has(item.measure_type)) return;
    if (!(item.measure_type in rates)) rates[item.measure_type] = Number(item.rate);
  });
  return rates;
}

function applyRatesButton(tariff, source) {
  const rates = applicableTariffRates(tariff);
  const keys = Object.keys(rates);
  state.tariffRateSources[source] = rates;
  if (!keys.length) return "";
  const summary = keys.map((key) => `${tariffMeasureLabels[key] || key} %${numberFormat.format(rates[key])}`).join(" · ");
  return `<div class="apply-rates"><div><b>Bulunan oranları maliyet hesabına aktar</b><small>${escapeHtml(summary)} · ${escapeHtml(tariff.gtip)}${tariff.origin_country ? ` · ${escapeHtml(tariff.origin_country)}` : ""}</small></div><button type="button" data-apply-rates="${escapeHtml(source)}">Bu oranları kullan</button></div>`;
}

function renderTariffTool(data) {
  const tariff = data.tariff || data;
  const cost = data.cost;
  const warnings = [...(tariff.warnings || []), ...(cost?.warnings || [])];
  const costLedger = cost ? `<div class="formula-ledger"><h3>Maliyet formülü · ${escapeHtml(cost.status)}</h3>
    ${(cost.lines || []).map((line) => `<div class="formula-line"><span>${escapeHtml(line.label)} <small>${escapeHtml(line.formula)}</small></span><code>${line.amount == null ? "—" : `${numberFormat.format(line.amount)} ${escapeHtml(cost.currency)}`}</code></div>`).join("")}
    <div class="formula-line"><strong>Toplam vergi</strong><code>${cost.total_taxes == null ? "Oran eksik" : `${numberFormat.format(cost.total_taxes)} ${escapeHtml(cost.currency)}`}</code></div>
    <div class="formula-line"><strong>Genel toplam (vergiler dahil)</strong><code>${cost.landed_total == null ? "Oran eksik" : `${numberFormat.format(cost.landed_total)} ${escapeHtml(cost.currency)}`}</code></div>
    <p class="rate-warning">Toplamlar sabit beyanname harcını içermez; kredili/vadeli ödemede KKDF eklenir, peşin ödemede bu kalem %0'dır. Kesin tutar için beyan öncesi gümrük müşaviri teyidi alın.</p></div>` : "";
  return `<div class="answer-head"><span class="answer-status${tariff.status === "matched" ? "" : " warning"}">${escapeHtml(tariff.status)}</span><div><h2>${escapeHtml(tariff.gtip)} · ${escapeHtml(tariff.origin_country || "menşe seçilmedi")}</h2><p>Ülke grubu: ${escapeHtml(tariff.resolved_country_group || "çözümlenmedi")} · ${escapeHtml(tariff.as_of)}</p></div></div>
    ${tariffMatchSummary(tariff)}
    <table class="evidence-table"><thead><tr><th>GTİP / Önlem</th><th>Oran</th><th>Menşe sütunu</th><th>Kaynak satırı</th><th>Kanıt</th></tr></thead><tbody>${tariffRows(tariff.measures)}</tbody></table>
    ${applyRatesButton(tariff, "tool")}
    ${tariff.conditional_measures?.length ? `<details class="advanced-fields"><summary><span>Şarta bağlı askıya alma / nihai kullanım satırları</span><small>${tariff.conditional_measures.length} kayıt</small></summary><table class="evidence-table"><tbody>${tariffRows(tariff.conditional_measures)}</tbody></table></details>` : ""}
    ${costLedger}
    ${warnings.length ? `<div class="result-caution">${warnings.map((item) => escapeHtml(item)).join(" · ")}</div>` : ""}
    ${data.legal_notice ? `<div class="legal-banner"><strong>Önemli:</strong> ${escapeHtml(data.legal_notice)}</div>` : ""}`;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-apply-rates]");
  if (!button) return;
  const rates = state.tariffRateSources[button.dataset.applyRates] || {};
  const applied = [];
  Object.entries(rates).forEach(([key, value]) => {
    const field = $(rateFieldByMeasure[key]);
    if (!field) return;
    field.value = String(value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    applied.push(tariffMeasureLabels[key] || key);
  });
  if (!applied.length) return showToast("Aktarılabilir doğrulanmış oran bulunamadı.");
  if (button.dataset.applyRates === "tool") {
    const code = $("#tariffGtip").value.trim();
    const origin = $("#tariffOrigin").value.trim();
    if (code && !$("#candidateGtip").value.trim()) { $("#candidateGtip").value = code; $("#candidateGtip").dispatchEvent(new Event("input", { bubbles: true })); }
    if (origin && !$("#originCountry").value.trim()) $("#originCountry").value = origin;
    const invoice = $("#tariffInvoice").value.trim();
    if (invoice && !$("#invoiceValue").value.trim()) { $("#invoiceValue").value = invoice; $("#freight").value = $("#tariffFreight").value || $("#freight").value; $("#insurance").value = $("#tariffInsurance").value || $("#insurance").value; $("#currency").value = $("#tariffCurrency").value; }
    switchCustomsView("assistant");
  }
  const costDetails = $("#costDetails");
  if (costDetails && "open" in costDetails) costDetails.open = true;
  $("#customsDutyRate")?.scrollIntoView({ behavior: "smooth", block: "center" });
  updateReadiness();
  showToast(`${applied.join(", ")} oranı maliyet alanlarına aktarıldı; analizi yeniden çalıştırın.`);
});

$("#tariffForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const output = $("#tariffOutput");
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true;
  output.innerHTML = '<div class="analysis-loading"><i></i><div><b>Resmî tarife satırları alınıyor</b><span>Menşe grubu, dipnot ve snapshot kanıtı denetleniyor…</span></div></div>';
  const common = { gtip: $("#tariffGtip").value.trim(), origin_country: $("#tariffOrigin").value.trim() };
  try {
    const invoice = nullableNumber("#tariffInvoice");
    const data = invoice == null
      ? await fetchJson("/api/tariff/lookup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(common) })
      : await fetchJson("/api/tariff/cost", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
          ...common, invoice_value: invoice, freight: nullableNumber("#tariffFreight") || 0,
          insurance: nullableNumber("#tariffInsurance") || 0, currency: $("#tariffCurrency").value,
          vat_rate: nullableNumber("#tariffVat"), payment_method: $("#tariffPayment").value || null,
        }) });
    output.innerHTML = renderTariffTool(data);
    const scenarioBox = $("#scenarioBox");
    if (scenarioBox) {
      scenarioBox.hidden = false;
      const input = $("#scenarioOrigins");
      if (input && !input.value.trim()) {
        const base = $("#tariffOrigin").value.trim();
        const candidates = ["Çin", "Almanya", "Güney Kore", "İtalya"]
          .filter((item) => item.toLocaleLowerCase("tr") !== base.toLocaleLowerCase("tr"));
        input.value = [base, ...candidates.slice(0, 2)].filter(Boolean).join(", ");
      }
    }
  } catch (error) {
    output.innerHTML = `<div class="answer-error"><h2>Tarife sorgusu tamamlanamadı</h2><p>${escapeHtml(error.message)}</p></div>`;
  } finally { button.disabled = false; }
});

function renderScenarioRows(data) {
  const fmt = (value) => value == null ? "kod başına değişiyor" : `%${numberFormat.format(value)}`;
  return `<div class="scenario-table-wrap"><table class="evidence-table"><thead><tr><th>Menşe</th><th>Sütun</th><th>Gümrük vergisi</th><th>İGV / ek vergi</th><th>Tercih belgesi</th><th>Not</th></tr></thead><tbody>${(data.rows || []).map((row) => {
    const docs = row.origin_documents;
    const docText = docs ? (docs.documents || []).map((item) => item.name).join(", ") : "—";
    const notes = (row.warnings || []).slice(0, 2);
    if (row.unambiguous_rates?.customs_duty == null) notes.push("Oran bütün alt GTİP12 satırlarında ortak değil");
    return `<tr><td><b>${escapeHtml(row.origin_country)}</b><small>${escapeHtml(docs?.regime_name || "")}</small></td><td>${escapeHtml(row.resolved_country_group || "—")}</td><td>${escapeHtml(fmt(row.unambiguous_rates?.customs_duty))}</td><td>${escapeHtml(fmt(row.unambiguous_rates?.additional_duty))}</td><td>${escapeHtml(docText)}</td><td>${escapeHtml(notes.join(" · ") || "—")}</td></tr>`;
  }).join("")}</tbody></table></div>
  <p class="rate-warning">Senaryo satırları resmî tarife arşivinin güncel snapshot'ından ve belge kural tablosundan üretilir; bağlayıcı tarife bilgisi değildir.</p>`;
}

$("#scenarioCompare").addEventListener("click", async () => {
  const output = $("#scenarioOutput");
  const gtip = $("#tariffGtip").value.trim();
  const origins = $("#scenarioOrigins").value.split(",").map((item) => item.trim()).filter(Boolean).slice(0, 6);
  if (!gtip || origins.length < 2) {
    output.innerHTML = '<p class="missing-list">Karşılaştırma için tarife kodu ve en az iki menşe ülke gerekir.</p>';
    return;
  }
  output.innerHTML = '<div class="analysis-loading"><i></i><div><b>Senaryolar karşılaştırılıyor</b><span>Her menşe için resmî sütun ve belge kuralı denetleniyor…</span></div></div>';
  try {
    const data = await fetchJson("/api/tariff/scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gtip, origins }),
    });
    output.innerHTML = renderScenarioRows(data);
  } catch (error) {
    output.innerHTML = `<div class="answer-error"><p>${escapeHtml(error.message)}</p></div>`;
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest("#printPrecheck")) return;
  document.body.classList.add("print-dossier");
  const cleanup = () => {
    document.body.classList.remove("print-dossier");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  window.print();
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("#emailPrecheck");
  if (!button) return;
  const result = state.currentCustomsResult;
  if (!result) { showToast("Gönderilecek ön değerlendirme dosyası bulunamadı."); return; }
  if (!state.auth?.authenticated) { showToast("E-posta ile göndermek için Google ile giriş yapın; dosya kendi adresinize gider."); return; }
  button.disabled = true;
  try {
    const data = await fetchJson("/api/email/precheck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    });
    showToast(`${data.recipient} adresine gönderildi; spam klasörünü de kontrol edin.`);
  } catch (error) {
    showToast(error.message || "E-posta gönderilemedi.");
  } finally {
    button.disabled = false;
  }
});

$("#ingestSource")?.addEventListener("click", async () => {
  const output = $("#ingestOutput");
  const url = $("#ingestUrl").value.trim();
  const file = $("#ingestPdf")?.files?.[0];
  if (!url && !file) { output.innerHTML = '<p class="missing-list">Belge adresi girin veya PDF dosyası seçin.</p>'; return; }
  if (url && file) { output.innerHTML = '<p class="missing-list">Yalnızca bir kaynak belirtin: adres veya PDF.</p>'; return; }
  output.innerHTML = '<div class="analysis-loading"><i></i><div><b>Belge okunuyor</b><span>Ürün metni çıkarılıyor, onayınıza sunulacak…</span></div></div>';
  try {
    let body;
    if (file) {
      if (file.size > 10 * 1024 * 1024) throw new Error("PDF en fazla 10 MB olabilir.");
      body = { pdf_data_url: await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error("PDF dosyası okunamadı."));
        reader.readAsDataURL(file);
      }) };
    } else {
      body = { url };
    }
    const data = await fetchJson("/api/customs/ingest-source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    output.innerHTML = `
      <p class="missing-list">${escapeHtml(data.warning || "")}</p>
      <textarea class="ingest-textarea" id="ingestText">${escapeHtml(data.text)}</textarea>
      <div class="result-actions"><button type="button" id="ingestAppend">Ürün tanımına ekle</button></div>
      ${data.truncated ? '<p class="missing-list">Belge uzun olduğu için metin kısaltıldı.</p>' : ""}`;
    $("#ingestAppend")?.addEventListener("click", () => {
      const target = $("#productDescription");
      const text = ($("#ingestText")?.value || "").trim();
      if (!target || !text) return;
      target.value = `${target.value ? `${target.value.trimEnd()} ` : ""}${text}`.slice(0, 2000);
      target.dispatchEvent(new Event("input", { bubbles: true }));
      showToast("Belge metni ürün tanımına eklendi; gözden geçirip onaylayın.");
    });
  } catch (error) {
    output.innerHTML = `<div class="answer-error"><p>${escapeHtml(error.message)}</p></div>`;
  }
});

function renderControlTool(data) {
  const cards = (data.matches || []).map((match) => {
    const rule = match.rule;
    return `<article class="control-card"><header><code>${escapeHtml(rule.code)}</code><b>${escapeHtml(rule.title)}</b><a href="${safeUrl(rule.source_url)}" target="_blank" rel="noreferrer">Resmî metin ↗</a></header>
      <dl><div><dt>Ek-1 eşleşmesi</dt><dd>${escapeHtml(match.matched_scope.gtip_prefix)} · ${escapeHtml(match.match_type)}</dd></div><div><dt>Sistem</dt><dd>${escapeHtml(rule.system)}</dd></div><div><dt>Fiilî denetim</dt><dd>${rule.risk_based ? "Risk analizine bağlı" : "Yetkili kurum kararı"}</dd></div><div><dt>Laboratuvar</dt><dd>${rule.laboratory_test_possible ? "Mümkün; otomatik değil" : "Metinde tespit edilmedi"}</dd></div></dl>
      <p><strong>Kapsam satırı:</strong> ${escapeHtml(match.matched_scope.source_line)}<br>${escapeHtml(match.assessment)}</p>
      ${rule.required_documents_excerpt ? `<details class="advanced-fields"><summary><span>Belge listesi özeti</span><small>Resmî metinden</small></summary><p>${escapeHtml(rule.required_documents_excerpt)}</p></details>` : ""}
      <div class="result-caution">${match.cautions.map((item) => escapeHtml(item)).join(" · ")}</div></article>`;
  }).join("");
  return `<div class="answer-head"><span class="answer-status${data.status === "matched" ? "" : " warning"}">${escapeHtml(data.status)}</span><div><h2>${escapeHtml(data.gtip)} kontrol dosyası</h2><p>${escapeHtml(data.as_of)} itibarıyla indekslenmiş resmî tebliğ ekleri · kapsam: ${escapeHtml(data.scope_determination || "belirsiz")} · fiilî denetim sonucu bu sistemde belirlenmez</p></div></div>
    ${cards || '<p class="missing-list">İndekslenen güncel Ek-1 listelerinde eşleşme bulunamadı.</p>'}
    ${(data.warnings || []).length ? `<div class="result-caution">${data.warnings.map((item) => escapeHtml(item)).join(" · ")}</div>` : ""}`;
}

$("#controlsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const output = $("#controlsOutput");
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true;
  output.innerHTML = '<div class="analysis-loading"><i></i><div><b>Kontrol tebliğleri taranıyor</b><span>Ek-1 kapsamı ile risk sonucu birbirinden ayrılıyor…</span></div></div>';
  try {
    const data = await fetchJson("/api/controls/lookup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gtip: $("#controlsGtip").value.trim() }) });
    output.innerHTML = renderControlTool(data);
  } catch (error) {
    output.innerHTML = `<div class="answer-error"><h2>Kontrol sorgusu tamamlanamadı</h2><p>${escapeHtml(error.message)}</p></div>`;
  } finally { button.disabled = false; }
});

function savedWatchItems() {
  try { return JSON.parse(localStorage.getItem("gumrukce-watchlist") || "[]"); } catch (_) { return []; }
}

function savedScenarios() {
  try { return JSON.parse(localStorage.getItem("gumrukce-scenarios") || "[]"); } catch (_) { return []; }
}

function renderWatchList() {
  const target = $("#watchList");
  const items = savedWatchItems();
  target.innerHTML = items.length ? items.map((item, index) => `<div class="watch-item"><code>${escapeHtml(item.gtip)}</code><span>${escapeHtml(item.label || "Adsız ürün")}</span><button type="button" data-watch-query="${index}">Kontrol et</button><button type="button" data-watch-remove="${index}">Kaldır</button></div>`).join("") : '<p class="missing-list">Bu cihazda izlenen GTİP yok.</p>';
  const scenarios = savedScenarios();
  $("#scenarioList").innerHTML = scenarios.length ? scenarios.map((item, index) => `<div class="watch-item"><code>${escapeHtml(item.gtip || "GTİP yok")}</code><span>${escapeHtml(item.title)}<small>${escapeHtml(formatDate(item.savedAt, true))} · ${escapeHtml(item.origin || "menşe yok")}</small></span><button type="button" data-scenario-open="${index}">Aç</button><button type="button" data-scenario-remove="${index}">Kaldır</button></div>`).join("") : '<p class="missing-list">Henüz kayıtlı ön değerlendirme yok.</p>';
}

$("#addWatch").addEventListener("click", () => {
  const gtip = $("#watchGtip").value.replace(/\D/g, "");
  if (gtip.length !== 12) return showToast("İzleme için 12 haneli GTİP girin.");
  const items = savedWatchItems();
  if (!items.some((item) => item.gtip === gtip)) items.push({ gtip, label: $("#watchLabel").value.trim(), addedAt: new Date().toISOString() });
  localStorage.setItem("gumrukce-watchlist", JSON.stringify(items.slice(-100)));
  renderWatchList();
  showToast("GTİP bu cihazdaki izleme listesine eklendi.");
});

$("#watchList").addEventListener("click", (event) => {
  const remove = event.target.closest("[data-watch-remove]");
  const query = event.target.closest("[data-watch-query]");
  if (remove) {
    const items = savedWatchItems(); items.splice(Number(remove.dataset.watchRemove), 1);
    localStorage.setItem("gumrukce-watchlist", JSON.stringify(items)); renderWatchList();
  }
  if (query) {
    const item = savedWatchItems()[Number(query.dataset.watchQuery)];
    if (!item) return;
    $("#controlsGtip").value = item.gtip; switchCustomsView("controls"); $("#controlsForm").requestSubmit();
  }
});

$("#scenarioList").addEventListener("click", (event) => {
  const open = event.target.closest("[data-scenario-open]");
  const remove = event.target.closest("[data-scenario-remove]");
  const items = savedScenarios();
  if (remove) {
    items.splice(Number(remove.dataset.scenarioRemove), 1);
    localStorage.setItem("gumrukce-scenarios", JSON.stringify(items)); renderWatchList();
  }
  if (open) {
    const item = items[Number(open.dataset.scenarioOpen)];
    if (!item?.result) return;
    switchCustomsView("assistant");
    $("#customsResult").hidden = false;
    renderCustomsResult(item.result);
    $("#customsResult").scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

async function loadChanges() {
  const output = $("#changesOutput");
  output.innerHTML = '<div class="analysis-loading"><i></i><div><b>Sürüm defteri okunuyor</b><span>Tarife ve kontrol snapshot’ları karşılaştırılıyor…</span></div></div>';
  try {
    const data = await fetchJson("/api/changes");
    const controlRows = data.controls || [];
    const changeSourceLabels = { import_regime: "İthalat Rejimi Kararı", additional_duty: "İlave Gümrük Vergisi (İGV) Kararı" };
    const changeStatusLabels = { no_previous_snapshot: "İlk sürüm arşivlendi", compared: "İki sürüm karşılaştırıldı" };
    const tariffSummaries = Object.entries(data.tariff || {}).map(([name, value]) => {
      const sourceLabel = changeSourceLabels[name] || name;
      const statusText = changeStatusLabels[value.status] || value.status || (value.changes?.length ? "değişiklik var" : "tek sürüm");
      const note = value.status === "no_previous_snapshot"
        ? "Karşılaştırılacak ikinci resmî sürüm henüz arşivlenmedi; sonraki sürüm güncellemesinden sonra satır farkları burada listelenir."
        : (value.message || `${value.changes?.length || 0} satır farkı`);
      return `<article class="candidate-card"><code>${escapeHtml(sourceLabel)}</code><b>${escapeHtml(statusText)}</b><p>${escapeHtml(note)}</p></article>`;
    }).join("");
    output.innerHTML = `<div class="candidate-grid">${tariffSummaries || '<p class="missing-list">Tarife sürümü henüz yok.</p>'}</div>
      <div class="formula-ledger"><h3>Kontrol tebliği değişiklikleri</h3>${controlRows.length ? controlRows.map((item) => `<div class="formula-line"><span><strong>${escapeHtml(item.code)}</strong> · ${escapeHtml(item.title)}<br><small>${escapeHtml(item.changed_at)}</small></span><code>${item.scope_count_delta > 0 ? "+" : ""}${escapeHtml(item.scope_count_delta)}</code></div>`).join("") : '<p class="missing-list">Karşılaştırılabilir ikinci tebliğ sürümü henüz oluşmadı.</p>'}</div>`;
  } catch (error) { output.innerHTML = `<div class="answer-error"><p>${escapeHtml(error.message)}</p></div>`; }
}

$("#refreshChanges").addEventListener("click", loadChanges);
renderWatchList();

const savedTheme = localStorage.getItem("ticaret-bilgi-theme");
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$("#themeToggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("ticaret-bilgi-theme", next);
});

loadCatalogStatus();
loadAuthState();
if (new URLSearchParams(location.search).get("scope") === "customs" || location.hash === "#customs") switchScope("customs");
runTicaretSearch({ offset: 0 });
