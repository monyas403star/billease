// shared helpers for all pages

async function apiGet(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  return res.json();
}

async function apiSend(url, method, data) {
  const res = await fetch(url, {
    method: method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: data ? JSON.stringify(data) : null,
  });
  return res.json();
}

function formToObj(form) {
  const out = {};
  new FormData(form).forEach((v, k) => { out[k] = v; });
  return out;
}

function showMsg(el, text, ok) {
  el.textContent = text;
  el.classList.remove("ok", "err");
  el.classList.add(ok ? "ok" : "err");
}

function fmtMoney(n) {
  return Number(n).toFixed(2) + " ₪";
}

function daysUntil(dateStr) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(dateStr);
  d.setHours(0, 0, 0, 0);
  return Math.round((d - today) / (1000 * 60 * 60 * 24));
}

function statusBadge(bill) {
  if (bill.is_paid) return '<span class="badge ok">שולם</span>';
  const days = daysUntil(bill.due_date);
  if (days < 0) return '<span class="badge late">באיחור</span>';
  if (days <= 7) return '<span class="badge warn">לתשלום בקרוב</span>';
  return '<span class="badge open">פתוח</span>';
}

// mobile nav toggle
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("nav-toggle");
  const nav = document.getElementById("topnav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => nav.classList.toggle("open"));
  }
});
