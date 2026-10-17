// add bill page - with recurring + category suggestion
const scanForm = document.getElementById("scan-form");
const scanFile = document.getElementById("scan-file");
const scanMsg = document.getElementById("scan-msg");
const preview = document.getElementById("preview");
const previewWrap = document.getElementById("preview-wrap");

const billForm = document.getElementById("bill-form");
const saveMsg = document.getElementById("save-msg");
const catSelect = document.getElementById("cat-select");
const catHint = document.getElementById("cat-hint");
const hiddenImage = document.getElementById("hidden-image");

const recToggle = document.getElementById("rec-toggle");
const recPeriod = document.getElementById("rec-period");

async function loadCategories() {
  const res = await apiGet("/api/categories");
  if (res.ok) {
    catSelect.innerHTML = res.categories
      .map(c => `<option value="${c}">${c}</option>`).join("");
  }
}
loadCategories();

// show/hide period select when "recurring" is toggled
recToggle.addEventListener("change", () => {
  recPeriod.classList.toggle("hidden", !recToggle.checked);
});

// suggest a category as the user types the supplier name
let suggestTimer = null;
billForm.supplier.addEventListener("input", () => {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(async () => {
    const s = billForm.supplier.value.trim();
    if (!s) { catHint.textContent = ""; return; }
    const res = await apiGet(`/api/suggest-category?supplier=${encodeURIComponent(s)}`);
    if (res.ok && res.category) {
      catSelect.value = res.category;
      catHint.textContent = `הקטגוריה ${res.category} סומנה אוטומטית לפי שם הספק`;
    } else {
      catHint.textContent = "";
    }
  }, 250);
});

scanFile.addEventListener("change", () => {
  const f = scanFile.files[0];
  if (!f) return;
  preview.src = URL.createObjectURL(f);
  previewWrap.classList.remove("hidden");
});

scanForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = scanFile.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("image", f);
  showMsg(scanMsg, "סורק...", true);
  const res = await fetch("/api/bills/scan", {
    method: "POST",
    body: fd,
    credentials: "same-origin",
  }).then(r => r.json());

  if (!res.ok) {
    showMsg(scanMsg, res.error || "הסריקה נכשלה", false);
    return;
  }
  if (res.image) hiddenImage.value = res.image;
  if (res.supplier) billForm.supplier.value = res.supplier;
  if (res.amount) billForm.amount.value = res.amount;
  if (res.due_date) billForm.due_date.value = res.due_date;
  if (res.category) {
    catSelect.value = res.category;
    catHint.textContent = `הקטגוריה ${res.category} סומנה אוטומטית`;
  }
  if (!res.ocr_available) {
    showMsg(scanMsg, "התמונה נשמרה. הזיהוי לא זמין - אנא מלא ידנית.", true);
  } else {
    showMsg(scanMsg, "נסרק. בדוק את השדות ושמור.", true);
  }
});

billForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(billForm);
  data.is_recurring = recToggle.checked;
  const res = await apiSend("/api/bills", "POST", data);
  if (res.ok) {
    showMsg(saveMsg, "החשבון נשמר! עובר לרשימת החשבונות...", true);
    setTimeout(() => { window.location.href = "/bills"; }, 800);
  } else {
    showMsg(saveMsg, res.error || "השמירה נכשלה", false);
  }
});
