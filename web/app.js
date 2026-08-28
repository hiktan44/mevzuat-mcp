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
      <span class="result-date">${escapeHtml(doc.gazette_date ? formatDate(doc.gazette_date) : "—")}</span>
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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch(state.scope === "ticaret" ? { offset: 0 } : { page: 1 });
});
$$('[data-scope]').forEach((button) => button.addEventListener("click", () => switchScope(button.dataset.scope)));
$$('.source-link').forEach((button) => button.addEventListener("click", () => {
  state.activeKind = button.dataset.kind;
  $$('.source-link').forEach((item) => item.classList.toggle("active", item === button));
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

function renderCustomsResult(data) {
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
      ${data.tariff_lookup ? `<section class="answer-section"><h3>Resmî tarife snapshot eşleşmesi</h3><table class="evidence-table"><thead><tr><th>GTİP / Önlem</th><th>Oran</th><th>Menşe sütunu</th><th>Kaynak satırı</th><th>Kanıt</th></tr></thead><tbody>${tariffRows(data.tariff_lookup.measures)}</tbody></table>${(data.tariff_lookup.warnings || []).length ? `<div class="result-caution">${data.tariff_lookup.warnings.map((item) => escapeHtml(item)).join(" · ")}</div>` : ""}</section>` : ""}
      ${data.control_lookup ? `<section class="answer-section"><h3>Resmî kontrol tebliği Ek-1 eşleşmeleri</h3>${renderControlTool(data.control_lookup)}</section>` : ""}
      <section class="answer-section"><h3>Eksik veya teyit edilmesi gereken bilgiler</h3><ul class="missing-list">${(data.missing_information?.length ? data.missing_information : ["Kritik eksik alan bildirilmedi."]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>
      <section class="answer-section"><h3>TAREKS · TSE · kimyasal · laboratuvar kontrolleri</h3>${renderFindings(data.controls, sourceMap)}</section>
      <section class="answer-section"><h3>Gerekli belge ve izinler</h3>${renderFindings(data.required_documents, sourceMap)}</section>
      <section class="answer-section"><h3>Vergi ve mali yükümlülük bulguları</h3>${renderFindings(data.taxes, sourceMap, "tax")}</section>
      <section class="answer-section"><h3>Kullanıcı oranlarıyla maliyet taslağı</h3>${renderCost(data.deterministic_cost)}</section>
      ${data.image_observation ? `<section class="answer-section"><h3>Fotoğrafta görülenler</h3><p class="missing-list">${escapeHtml(data.image_observation)}</p></section>` : ""}
      <section class="answer-section"><h3>Sonraki güvenli adımlar</h3><ol class="next-list">${(data.next_steps || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></section>
      <section class="answer-section"><h3>Resmî kanıt defteri · ${(data.sources || []).length} kaynak</h3><div class="source-ledger">${sources}</div></section>
      <div class="legal-banner"><strong>Önemli:</strong> ${escapeHtml(data.legal_notice)}</div>
      <div class="result-actions"><button id="saveScenario" type="button">Bu ön değerlendirmeyi kaydet</button></div>
    </article>
    <form class="followup-box" id="followupForm"><label class="field"><span>Bu ürün için takip sorusu</span><input id="followupQuestion" maxlength="1500" placeholder="Örn. TAREKS başvurusunda hangi teknik dosyalar hazırlanmalı?"></label><button class="analyse-button" type="submit"><span>Takip sorusunu sor</span><svg viewBox="0 0 24 24"><path d="m5 12 14 0M14 6l6 6-6 6"/></svg></button></form>`;
  $("#followupForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = $("#followupQuestion").value.trim();
    if (!value) return;
    $("#customsQuestion").value = value;
    $("#customsForm").requestSubmit();
  });
  $("#saveScenario")?.addEventListener("click", () => {
    const items = savedScenarios();
    items.unshift({
      id: crypto.randomUUID?.() || String(Date.now()),
      savedAt: new Date().toISOString(),
      title: data.inquiry?.product_description || $("#productDescription").value.trim() || "İthalat ön değerlendirmesi",
      gtip: data.inquiry?.candidate_gtip || $("#candidateGtip").value.trim(),
      origin: data.inquiry?.origin_country || $("#originCountry").value.trim(),
      result: data,
    });
    try {
      localStorage.setItem("gumrukce-scenarios", JSON.stringify(items.slice(0, 20)));
      showToast("Ön değerlendirme bu cihazda kaydedildi.");
    } catch (_) { showToast("Tarayıcı depolama alanı dolu; dosya kaydedilemedi."); }
  });
}

function updateReadiness() {
  const checks = {
    vision: !state.customsImageData || state.customsVisionStatus === "confirmed",
    description: $("#productDescription").value.trim().length >= 12,
    origin: Boolean($("#originCountry").value.trim()),
    gtip: $("#candidateGtip").value.replace(/\D/g, "").length >= 4,
    cost: ["#invoiceValue", "#freight", "#insurance"].every((selector) => $(selector).value !== ""),
    payment: Boolean($("#paymentMethod").value.trim() && $("#incoterm").value.trim()),
  };
  Object.entries(checks).forEach(([key, ready]) => {
    $(`[data-check="${key}"]`)?.classList.toggle("ready", ready);
  });
}

const visionFieldSelectors = [
  "#productDescription", "#composition", "#intendedUse", "#productCategory", "#brandModel",
  "#dimensions", "#labelText", "#visibleFeatures", "#inferredFeatures", "#classificationQuestions",
];

function setVisionState(status, message, provider = "") {
  state.customsVisionStatus = status;
  const labels = {
    idle: "Bekliyor", analysing: "Analiz ediliyor", review: "Kullanıcı kontrolü", confirmed: "Onaylandı", error: "Elle doldurun",
  };
  const panel = $("#attributeReview");
  if (panel) panel.hidden = !state.customsImageData;
  const badge = $("#visionState");
  badge.dataset.state = status;
  badge.textContent = labels[status] || status;
  $("#visionMessage").textContent = message;
  $("#visionProvider").textContent = provider || "Model bilgisi analizden sonra gösterilir.";
  const confirm = $("#confirmAttributes");
  confirm.disabled = status === "analysing";
  confirm.querySelector("span").textContent = status === "confirmed"
    ? "Evsaflar onaylandı · Değişiklikte tekrar onaylayın"
    : "Evsafları onayla ve araştırmaya hazırla";
  updateReadiness();
}

function joinLines(values) {
  return Array.isArray(values) ? values.filter(Boolean).join("\n") : "";
}

function applyVisionAttributes(data) {
  const description = data.product_description || [data.product_name, data.product_category].filter(Boolean).join(" — ");
  $("#productDescription").value = description;
  $("#composition").value = data.composition || "";
  $("#intendedUse").value = data.intended_use || "";
  $("#productCategory").value = data.product_category || "";
  $("#brandModel").value = [data.visible_brand, data.visible_model].filter(Boolean).join(" / ");
  $("#dimensions").value = data.dimensions || "";
  $("#labelText").value = data.label_text || "";
  $("#visibleFeatures").value = joinLines(data.visible_features);
  $("#inferredFeatures").value = joinLines(data.inferred_features);
  $("#classificationQuestions").value = joinLines(data.classification_questions);
  updateReadiness();
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
    $("#attributeReview").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    state.customsVisionResult = null;
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
    state.customsVisionStatus = "idle";
    $("#imagePreview").hidden = true;
    $("#uploadZone").classList.remove("has-image");
    $("#attributeReview").hidden = true;
    $("#uploadTitle").textContent = "Ürün fotoğrafı ekle";
    $("#uploadHint").textContent = "Yüklenince görsel evsaf analizi otomatik başlar";
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
  $("#uploadHint").textContent = `${numberFormat.format(Math.ceil(file.size / 1024))} KB · sunucuda saklanmaz`;
  await analyseProductImage();
}

function customsRequestBody() {
  return {
    question: $("#customsQuestion").value.trim(),
    product_description: $("#productDescription").value.trim(),
    candidate_gtip: $("#candidateGtip").value.trim() || null,
    origin_country: $("#originCountry").value.trim() || null,
    dispatch_country: $("#dispatchCountry").value.trim() || null,
    intended_use: $("#intendedUse").value.trim() || null,
    composition: $("#composition").value.trim() || null,
    product_category: $("#productCategory").value.trim() || null,
    brand_model: $("#brandModel").value.trim() || null,
    dimensions: $("#dimensions").value.trim() || null,
    label_text: $("#labelText").value.trim() || null,
    visible_features: $("#visibleFeatures").value.trim() || null,
    inferred_features: $("#inferredFeatures").value.trim() || null,
    classification_questions: $("#classificationQuestions").value.trim() || null,
    condition: $("#productCondition").value,
    invoice_value: nullableNumber("#invoiceValue"),
    freight: nullableNumber("#freight"),
    insurance: nullableNumber("#insurance"),
    other_pre_import_costs: nullableNumber("#otherCosts"),
    currency: $("#currency").value,
    incoterm: $("#incoterm").value.trim() || null,
    payment_method: $("#paymentMethod").value.trim() || null,
    customs_duty_rate: nullableNumber("#customsDutyRate"),
    additional_duty_rate: nullableNumber("#additionalDutyRate"),
    vat_rate: nullableNumber("#vatRate"),
  };
}

$("#productImage").addEventListener("change", (event) => setProductImage(event.target.files?.[0]).catch(() => showToast("Görsel okunamadı.")));
const uploadZone = $("#uploadZone");
["dragenter", "dragover"].forEach((name) => uploadZone.addEventListener(name, (event) => { event.preventDefault(); uploadZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((name) => uploadZone.addEventListener(name, (event) => { event.preventDefault(); uploadZone.classList.remove("dragging"); }));
uploadZone.addEventListener("drop", (event) => setProductImage(event.dataTransfer.files?.[0]).catch(() => showToast("Görsel okunamadı.")));
$$('#customsForm input, #customsForm textarea, #customsForm select').forEach((input) => input.addEventListener("input", updateReadiness));
visionFieldSelectors.forEach((selector) => $(selector)?.addEventListener("input", () => {
  if (state.customsImageData && state.customsVisionStatus === "confirmed") {
    setVisionState(
      "review",
      "Onaydan sonra evsaf değişti. Güncel alanları yeniden onaylamadan resmî araştırma başlatılamaz.",
      state.customsVisionResult ? `Görsel model: ${state.customsVisionResult.provider} · ${state.customsVisionResult.model}` : "Elle düzenlenen evsaf",
    );
  }
}));

$("#confirmAttributes").addEventListener("click", () => {
  if (state.customsVisionStatus === "analysing") return;
  if ($("#productDescription").value.trim().length < 12) {
    showToast("Onaylamadan önce teknik ürün tanımını tamamlayın.");
    $("#productDescription").focus();
    return;
  }
  setVisionState(
    "confirmed",
    "Evsaflar kullanıcı tarafından onaylandı. GTİP, e-vergi ve TAREKS araştırması artık başlatılabilir.",
    state.customsVisionResult
      ? `Görsel model: ${state.customsVisionResult.provider} · ${state.customsVisionResult.model} · kullanıcı onaylı`
      : "Elle girilen evsaf · kullanıcı onaylı",
  );
  showToast("Ürün evsafları onaylandı.");
});

$("#customsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.customsImageData && state.customsVisionStatus !== "confirmed") {
    showToast("Önce fotoğraftan çıkarılan evsafları kontrol edip onaylayın.");
    $("#attributeReview").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
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
    button.querySelector("span").textContent = "Onaylanan evsaflarla resmî araştırmayı başlat";
  }
});

function switchCustomsView(view) {
  $$('[data-customs-view]').forEach((button) => button.classList.toggle("active", button.dataset.customsView === view));
  $$('[data-customs-panel]').forEach((panel) => { panel.hidden = panel.dataset.customsPanel !== view; });
  if (view === "changes") {
    renderWatchList();
    loadChanges();
  }
}

$$('[data-customs-view]').forEach((button) => button.addEventListener("click", () => switchCustomsView(button.dataset.customsView)));

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

function renderTariffTool(data) {
  const tariff = data.tariff || data;
  const cost = data.cost;
  const warnings = [...(tariff.warnings || []), ...(cost?.warnings || [])];
  const costLedger = cost ? `<div class="formula-ledger"><h3>Maliyet formülü · ${escapeHtml(cost.status)}</h3>
    ${(cost.lines || []).map((line) => `<div class="formula-line"><span>${escapeHtml(line.label)} <small>${escapeHtml(line.formula)}</small></span><code>${line.amount == null ? "—" : `${numberFormat.format(line.amount)} ${escapeHtml(cost.currency)}`}</code></div>`).join("")}
    <div class="formula-line"><strong>İthal edilmiş toplam</strong><code>${cost.landed_total == null ? "Oran eksik" : `${numberFormat.format(cost.landed_total)} ${escapeHtml(cost.currency)}`}</code></div></div>` : "";
  return `<div class="answer-head"><span class="answer-status${tariff.status === "matched" ? "" : " warning"}">${escapeHtml(tariff.status)}</span><div><h2>${escapeHtml(tariff.gtip)} · ${escapeHtml(tariff.origin_country || "menşe seçilmedi")}</h2><p>Ülke grubu: ${escapeHtml(tariff.resolved_country_group || "çözümlenmedi")} · ${escapeHtml(tariff.as_of)}</p></div></div>
    <table class="evidence-table"><thead><tr><th>GTİP / Önlem</th><th>Oran</th><th>Menşe sütunu</th><th>Kaynak satırı</th><th>Kanıt</th></tr></thead><tbody>${tariffRows(tariff.measures)}</tbody></table>
    ${tariff.conditional_measures?.length ? `<details class="advanced-fields"><summary><span>Şarta bağlı askıya alma / nihai kullanım satırları</span><small>${tariff.conditional_measures.length} kayıt</small></summary><table class="evidence-table"><tbody>${tariffRows(tariff.conditional_measures)}</tbody></table></details>` : ""}
    ${costLedger}
    ${warnings.length ? `<div class="result-caution">${warnings.map((item) => escapeHtml(item)).join(" · ")}</div>` : ""}
    ${data.legal_notice ? `<div class="legal-banner"><strong>Önemli:</strong> ${escapeHtml(data.legal_notice)}</div>` : ""}`;
}

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
          vat_rate: nullableNumber("#tariffVat"),
        }) });
    output.innerHTML = renderTariffTool(data);
  } catch (error) {
    output.innerHTML = `<div class="answer-error"><h2>Tarife sorgusu tamamlanamadı</h2><p>${escapeHtml(error.message)}</p></div>`;
  } finally { button.disabled = false; }
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
  return `<div class="answer-head"><span class="answer-status${data.status === "matched" ? "" : " warning"}">${escapeHtml(data.status)}</span><div><h2>${escapeHtml(data.gtip)} kontrol dosyası</h2><p>${escapeHtml(data.as_of)} itibarıyla indekslenmiş resmî tebliğ ekleri</p></div></div>
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
    const tariffSummaries = Object.entries(data.tariff || {}).map(([name, value]) => `<article class="candidate-card"><code>${escapeHtml(name)}</code><b>${escapeHtml(value.status || (value.changes?.length ? "değişiklik" : "tek sürüm"))}</b><p>${escapeHtml(value.message || `${value.changes?.length || 0} satır farkı`)}</p></article>`).join("");
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
runTicaretSearch({ offset: 0 });
