// my bills page with filter chips
const tbody = document.getElementById("bills-body");
const chips = document.querySelectorAll(".chip");

let allBills = [];
let currentFilter = "all";

function passes(b, f) {
  if (f === "all") return true;
  if (b.is_paid) return false;
  const d = daysUntil(b.due_date);
  if (f === "open") return true;
  if (f === "soon") return d >= 0 && d <= 7;
  if (f === "late") return d < 0;
  return true;
}

function render() {
  const list = allBills.filter(b => passes(b, currentFilter));
  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6">
      <div class="empty"><span class="emoji">📭</span>${t("אין חשבונות להצגה")}</div>
    </td></tr>`;
    return;
  }
  tbody.innerHTML = list.map(b => {
    const recIcon = b.is_recurring
      ? `<span class="rec-icon" title="${b.recurrence === 'yearly' ? t("חוזר שנתי") : t("חוזר חודשי")}">🔄</span>`
      : "";
    const imgIcon = b.image_path
      ? `<a href="/uploads/${b.image_path}" target="_blank" class="rec-icon" title="${escapeHtml(t("צפייה בתמונת מקור"))}">📷</a>`
      : "";
    return `
      <tr>
        <td>${escapeHtml(b.supplier || "")} ${recIcon}${imgIcon}</td>
        <td>${fmtMoney(b.amount)}</td>
        <td>${escapeHtml(categoryLabel(b.category || ""))}</td>
        <td>${escapeHtml(fmtDate(b.due_date))}</td>
        <td>${statusBadge(b)}</td>
        <td>
          ${b.is_paid ? "" :
            `<button class="btn primary small" data-pay="${b.bill_id}">${t("שולם")}</button>`}
          <button class="btn small danger" data-del="${b.bill_id}">${t("מחיקה")}</button>
        </td>
      </tr>`;
  }).join("");
}

async function loadBills() {
  const res = await apiGet("/api/bills");
  if (!res.ok) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted">${t("שגיאת טעינה")}</td></tr>`;
    return;
  }
  allBills = res.bills;
  render();
}

chips.forEach(c => {
  c.addEventListener("click", () => {
    chips.forEach(x => x.classList.remove("is-active"));
    c.classList.add("is-active");
    currentFilter = c.dataset.filter;
    render();
  });
});

tbody.addEventListener("click", async (e) => {
  const payId = e.target.getAttribute("data-pay");
  const delId = e.target.getAttribute("data-del");
  if (payId) {
    const b = allBills.find(x => x.bill_id == payId);
    const extra = b && b.is_recurring ? t(" חשבון חדש לחודש הבא ייווצר אוטומטית.") : "";
    if (!confirm(t("לסמן את החשבון כשולם?") + extra)) return;
    await apiSend(`/api/bills/${payId}/pay`, "POST");
    loadBills();
  }
  if (delId) {
    if (!confirm(t("למחוק את החשבון?"))) return;
    await apiSend(`/api/bills/${delId}`, "DELETE");
    loadBills();
  }
});

loadBills();
