// admin dashboard (אפיון 11.2)
async function load() {
  const [stats, users] = await Promise.all([
    apiGet("/api/admin/stats"),
    apiGet("/api/admin/users"),
  ]);

  if (stats.ok) {
    document.getElementById("adm-users").textContent = stats.users;
    document.getElementById("adm-bills").textContent = stats.bills;
    document.getElementById("adm-signups").textContent = stats.signups_today;
    document.getElementById("adm-today-bills").textContent = stats.bills_today;

    const catBody = document.getElementById("adm-cats");
    if (stats.by_category.length === 0) {
      catBody.innerHTML = `<tr><td colspan="3" class="muted">${t("אין נתונים")}</td></tr>`;
    } else {
      catBody.innerHTML = stats.by_category.map(r => `
        <tr>
          <td>${escapeHtml(categoryLabel(r.category) || t("(ללא)"))}</td>
          <td>${r.cnt}</td>
          <td>${fmtMoney(r.total)}</td>
        </tr>`).join("");
    }
  }

  if (users.ok) {
    const tbody = document.getElementById("adm-users-tbl");
    tbody.innerHTML = users.users.map(u => `
      <tr>
        <td>${escapeHtml(u.full_name || "")}</td>
        <td>${escapeHtml(u.email || "")}</td>
        <td>${u.bill_count}</td>
        <td>${escapeHtml(u.created_at || "")}</td>
        <td>${u.is_admin ? `<span class="badge ok">${t("מנהל")}</span>` : ""}</td>
      </tr>`).join("");
  }

}
load();
