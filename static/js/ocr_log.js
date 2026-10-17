// OCR audit page (אפיון 11.1.4)
async function load() {
  const res = await apiGet("/api/ocr-log");
  if (!res.ok) return;

  const billsTbody = document.getElementById("ocr-bills");
  if (res.bills.length === 0) {
    billsTbody.innerHTML = '<tr><td colspan="6" class="muted">עדיין אין חשבונות שנסרקו</td></tr>';
  } else {
    billsTbody.innerHTML = res.bills.map(b => `
      <tr>
        <td>${b.image_path
          ? `<a href="/uploads/${b.image_path}" target="_blank"><img class="thumb" src="/uploads/${b.image_path}" alt="thumb"></a>`
          : '<span class="muted">אין</span>'}</td>
        <td>${b.supplier || ""}</td>
        <td>${fmtMoney(b.amount)}</td>
        <td>${b.category || ""}</td>
        <td>${b.due_date}</td>
        <td>${b.image_path
          ? `<a class="link-btn" href="/uploads/${b.image_path}" target="_blank">פתיחה ←</a>`
          : ""}</td>
      </tr>`).join("");
  }

  const logTbody = document.getElementById("ocr-log");
  if (res.log.length === 0) {
    logTbody.innerHTML = '<tr><td colspan="4" class="muted">אין רשומות בלוג</td></tr>';
  } else {
    logTbody.innerHTML = res.log.map(r => `
      <tr>
        <td>${r.created_at}</td>
        <td><a href="/uploads/${r.image_path}" target="_blank">${r.image_path}</a></td>
        <td>${r.parsed_ok
          ? '<span class="badge ok">הצליח</span>'
          : '<span class="badge late">נכשל</span>'}</td>
        <td>${r.note || ""}</td>
      </tr>`).join("");
  }
}
load();
