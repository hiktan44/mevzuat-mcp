const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const formatDate = (value) => value ? new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(Number(value) * 1000)) : "—";
function toast(message) { const node = $("#toast"); node.textContent = message; node.classList.add("visible"); setTimeout(() => node.classList.remove("visible"), 2200); }
async function json(url, options) { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || "İstek tamamlanamadı."); return data; }

async function load() {
  try {
    const data = await json("/api/admin/overview");
    $("#adminUserCount").textContent = data.users.length;
    const stats = { "Kanıt dosyaları": data.dossier_count, "Görsel analiz": data.usage.vision || 0, "GTİP adayı": data.usage.classification || 0, "Ön değerlendirme": data.usage.precheck || 0 };
    $("#adminStats").innerHTML = Object.entries(stats).map(([label, value]) => `<article class="quota-card"><header><b>${escapeHtml(label)}</b><span>bu ay</span></header><strong>${escapeHtml(value)}</strong></article>`).join("");
    $("#adminUsers").innerHTML = data.users.map((user) => `<tr data-user="${escapeHtml(user.google_sub)}"><td><b>${escapeHtml(user.name || "Adsız")}</b><small>${escapeHtml(user.email)}</small></td><td><select data-plan><option value="starter">Başlangıç</option><option value="expert">Uzman</option><option value="team">Ekip</option><option value="institutional">Kurumsal</option></select></td><td><select data-status><option value="active">Aktif</option><option value="pending">Bekliyor</option><option value="past_due">Ödeme gecikmiş</option><option value="cancelled">İptal</option></select></td><td>${escapeHtml(formatDate(user.last_login_at))}</td><td><button type="button" data-save>Kaydet</button></td></tr>`).join("");
    data.users.forEach((user) => { const row = $(`[data-user="${CSS.escape(user.google_sub)}"]`); row.querySelector("[data-plan]").value = user.plan_code; row.querySelector("[data-status]").value = user.subscription_status; });
  } catch (error) { $("#adminUsers").innerHTML = `<tr><td colspan="5">${escapeHtml(error.message)}</td></tr>`; }
}

$("#adminUsers").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-save]"); if (!button) return;
  const row = button.closest("[data-user]"); button.disabled = true;
  try { await json(`/api/admin/subscriptions/${encodeURIComponent(row.dataset.user)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan_code: row.querySelector("[data-plan]").value, status: row.querySelector("[data-status]").value }) }); toast("Abonelik güncellendi ve denetim kaydı oluşturuldu."); }
  catch (error) { toast(error.message); } finally { button.disabled = false; }
});
load();
