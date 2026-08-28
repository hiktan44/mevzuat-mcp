const state = {
  page: 1,
  pageSize: 20,
  lastRequest: null,
  currentDocument: "",
  currentTrigger: null,
};

const form = document.querySelector("#searchForm");
const queryInput = document.querySelector("#query");
const typeInput = document.querySelector("#type");
const startDateInput = document.querySelector("#startDate");
const endDateInput = document.querySelector("#endDate");
const statusCard = document.querySelector("#status");
const resultList = document.querySelector("#resultList");
const resultCount = document.querySelector("#resultCount");
const resultsTitle = document.querySelector("#resultsTitle");
const pagination = document.querySelector("#pagination");
const prevPage = document.querySelector("#prevPage");
const nextPage = document.querySelector("#nextPage");
const pageLabel = document.querySelector("#pageLabel");
const reader = document.querySelector("#reader");
const readerTitle = document.querySelector("#readerTitle");
const readerMeta = document.querySelector("#readerMeta");
const readerContent = document.querySelector("#readerContent");
const readerLength = document.querySelector("#readerLength");
const readerSearch = document.querySelector("#readerSearch");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function currentMode() {
  return form.querySelector('input[name="mode"]:checked').value;
}

function setLoading() {
  statusCard.hidden = true;
  pagination.hidden = true;
  resultList.innerHTML = Array.from({ length: 5 }, () => '<div class="skeleton" aria-hidden="true"></div>').join("");
  resultCount.textContent = "Kaynak taranıyor…";
}

function setStatus(title, message, isError = false) {
  resultList.innerHTML = "";
  pagination.hidden = true;
  statusCard.hidden = false;
  statusCard.querySelector("strong").textContent = title;
  statusCard.querySelector("p").textContent = message;
  statusCard.querySelector(".status-seal").textContent = isError ? "!" : "§";
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("tr-TR").format(date);
}

function renderResults(data) {
  statusCard.hidden = true;
  resultList.innerHTML = "";
  resultCount.textContent = `${new Intl.NumberFormat("tr-TR").format(data.total)} kayıt`;
  pageLabel.textContent = `Sayfa ${data.page}`;
  prevPage.disabled = data.page <= 1;
  nextPage.disabled = !data.has_next;
  pagination.hidden = data.total <= data.page_size;

  if (!data.documents.length) {
    setStatus("Bu ölçütlerle sonuç bulunamadı.", "Daha kısa bir ifade deneyin veya mevzuat türü filtresini kaldırın.");
    resultCount.textContent = "0 kayıt";
    return;
  }

  for (const doc of data.documents) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-item";
    button.dataset.documentId = doc.id;
    button.dataset.title = doc.title;
    button.dataset.number = doc.number;
    const meta = [
      doc.type_label,
      doc.gazette_date ? `RG ${formatDate(doc.gazette_date)}` : "",
      doc.gazette_number ? `Sayı ${doc.gazette_number}` : "",
    ].filter(Boolean);
    button.innerHTML = `
      <span class="result-number">${escapeHtml(doc.number ? `No ${doc.number}` : "Numarasız")}</span>
      <span>
        <strong class="result-title">${escapeHtml(doc.title)}</strong>
        <span class="result-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</span>
      </span>
      <span class="result-arrow" aria-hidden="true">→</span>
    `;
    button.addEventListener("click", () => openDocument(doc, button));
    resultList.append(button);
  }
}

async function runSearch({ page = 1 } = {}) {
  const request = {
    query: queryInput.value.trim(),
    mode: currentMode(),
    type: typeInput.value,
    start_date: startDateInput.value || null,
    end_date: endDateInput.value || null,
    page,
    page_size: state.pageSize,
  };

  state.lastRequest = request;
  state.page = page;
  resultsTitle.textContent = request.query ? `“${request.query}” için sonuçlar` : "Son yayımlanan mevzuat";
  setLoading();
  document.querySelector("#results").scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Arama tamamlanamadı.");
    renderResults(data);
  } catch (error) {
    resultCount.textContent = "Arama başarısız";
    setStatus("Arama tamamlanamadı.", error.message || "Bağlantınızı kontrol edip yeniden deneyin.", true);
  }
}

async function openDocument(documentData, trigger) {
  state.currentTrigger = trigger;
  state.currentDocument = "";
  readerTitle.textContent = documentData.title;
  readerMeta.textContent = [documentData.number && `No ${documentData.number}`, documentData.type_label].filter(Boolean).join(" · ");
  readerContent.textContent = "Mevzuat metni kaynağından alınıyor…";
  readerLength.textContent = "";
  readerSearch.value = "";
  reader.classList.add("open");
  reader.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  reader.querySelector(".reader-close").focus();

  try {
    const response = await fetch(`/api/document/${encodeURIComponent(documentData.id)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Metin yüklenemedi.");
    state.currentDocument = data.content;
    readerContent.textContent = data.content;
    readerLength.textContent = `${new Intl.NumberFormat("tr-TR").format(data.content.length)} karakter`;
  } catch (error) {
    readerContent.textContent = error.message || "Metin yüklenemedi.";
  }
}

function closeReader() {
  reader.classList.remove("open");
  reader.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  state.currentTrigger?.focus();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch({ page: 1 });
});

document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.query;
    typeInput.value = button.dataset.type || "";
    form.querySelector(`input[name="mode"][value="${button.dataset.mode}"]`).checked = true;
    runSearch({ page: 1 });
  });
});

prevPage.addEventListener("click", () => runSearch({ page: Math.max(1, state.page - 1) }));
nextPage.addEventListener("click", () => runSearch({ page: state.page + 1 }));

document.querySelectorAll("[data-close-reader]").forEach((element) => element.addEventListener("click", closeReader));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && reader.classList.contains("open")) closeReader();
});

readerSearch.addEventListener("input", () => {
  const term = readerSearch.value.trim();
  readerContent.textContent = state.currentDocument;
  if (!term || !state.currentDocument) return;
  const index = state.currentDocument.toLocaleLowerCase("tr-TR").indexOf(term.toLocaleLowerCase("tr-TR"));
  if (index >= 0) {
    const before = state.currentDocument.slice(0, index);
    readerContent.textContent = state.currentDocument;
    requestAnimationFrame(() => {
      const approximateLine = before.split("\n").length;
      readerContent.scrollTop = Math.max(0, (approximateLine - 3) * 27);
    });
  }
});

const themeToggle = document.querySelector("#themeToggle");
const savedTheme = localStorage.getItem("mevzuat-theme");
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
themeToggle.addEventListener("click", () => {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nextTheme;
  localStorage.setItem("mevzuat-theme", nextTheme);
});
