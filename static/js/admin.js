// admin dashboard (אפיון 11.2)
async function load() {
  const [stats, users, log] = await Promise.all([
    apiGet("/api/admin/stats"),
    apiGet("/api/admin/users"),
    apiGet("/api/admin/ocr-log"),
  ]);

  if (stats.ok) {
    document.getElementById("adm-users").textContent = stats.users;
    document.getElementById("adm-bills").textContent = stats.bills;
    document.getElementById("adm-ocr").textContent = stats.ocr_scans;
    document.getElementById("adm-fails").textContent = stats.ocr_fails;
    document.getElementById("adm-signups").textContent = stats.signups_today;
    document.getElementById("adm-today-bills").textContent = stats.bills_today;

    const catBody = document.getElementById("adm-cats");
    if (stats.by_category.length === 0) {
      catBody.innerHTML = '<tr><td colspan="3" class="muted">אין נתונים</td></tr>';
    } else {
      catBody.innerHTML = stats.by_category.map(r => `
        <tr>
          <td>${r.category || "(ללא)"}</td>
          <td>${r.cnt}</td>
          <td>${fmtMoney(r.total)}</td>
        </tr>`).join("");
    }
  }

  if (users.ok) {
    const tbody = document.getElementById("adm-users-tbl");
    tbody.innerHTML = users.users.map(u => `
      <tr>
        <td>${u.user_id}</td>
        <td>${u.full_name}</td>
        <td>${u.email}</td>
        <td>${u.bill_count}</td>
        <td>${u.created_at}</td>
        <td>${u.is_admin ? '<span class="badge ok">מנהל</span>' : ""}</td>
      </tr>`).join("");
  }

  if (log.ok) {
    const tbody = document.getElementById("adm-ocr-log");
    if (log.log.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">אין רשומות</td></tr>';
    } else {
      tbody.innerHTML = log.log.map(r => `
        <tr>
          <td>${r.created_at}</td>
          <td>${r.user_id}</td>
          <td><a href="/uploads/${r.image_path}" target="_blank">${r.image_path}</a></td>
          <td>${r.parsed_ok ? '<span class="badge ok">הצליח</span>' : '<span class="badge late">נכשל</span>'}</td>
          <td>${r.note || ""}</td>
        </tr>`).join("");
    }
  }
}
load();
