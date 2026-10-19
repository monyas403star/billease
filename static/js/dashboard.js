// dashboard page
const tbody = document.getElementById("upcoming-body");

async function loadDashboard() {
  const res = await apiGet("/api/bills");
  if (!res.ok) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">לא ניתן לטעון חשבונות</td></tr>';
    return;
  }
  const bills = res.bills;

  const open = bills.filter(b => !b.is_paid);
  const paid = bills.filter(b => b.is_paid);
  const total = open.reduce((s, b) => s + b.amount, 0);
  const soon = open.filter(b => {
    const d = daysUntil(b.due_date);
    return d >= 0 && d <= 7;
  }).length;

  document.getElementById("stat-open").textContent = open.length;
  document.getElementById("stat-total").textContent = fmtMoney(total);
  document.getElementById("stat-soon").textContent = soon;
  document.getElementById("stat-paid").textContent = paid.length;

  const upcoming = open
    .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
    .slice(0, 5);

  if (upcoming.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">
      <div class="empty"><span class="emoji">🎉</span>אין חשבונות פתוחים. כל הכבוד!</div>
    </td></tr>`;
    return;
  }
  tbody.innerHTML = upcoming.map(b => `
    <tr>
      <td>${b.supplier}</td>
      <td>${fmtMoney(b.amount)}</td>
      <td>${b.category || ""}</td>
      <td>${b.due_date}</td>
      <td>${statusBadge(b)}</td>
    </tr>
  `).join("");
}

loadDashboard();
