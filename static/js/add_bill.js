// BillEase - add bill page

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

const installmentToggle = document.getElementById('installment-toggle');
const installmentFields = document.getElementById('installment-fields');
const paymentRows = document.getElementById('payment-rows');
const paymentCount = document.getElementById('payment-count');
function setInstallments(enabled) {
  installmentToggle.checked = enabled;
  installmentFields.classList.toggle('hidden', !enabled);
  paymentRows.querySelectorAll('input').forEach(input => input.disabled = !enabled);
  recToggle.disabled = enabled;
  if (enabled) { recToggle.checked = false; recPeriod.classList.add('hidden'); }
}
function renderPayments(rows) {
  paymentRows.replaceChildren();
  rows.forEach((payment, index) => {
    const row = document.createElement('div');
    row.className = 'payment-row';
    const label = document.createElement('span');
    label.textContent = String(index + 1);
    const amount = document.createElement('input');
    Object.assign(amount, {type: 'number', min: '0.01', max: '999999999.99', step: '0.01', required: true, value: payment.amount ?? ''});
    amount.dataset.field = 'amount';
    amount.setAttribute('aria-label', t('Payment amount') + ' ' + (index + 1));
    const date = document.createElement('input');
    Object.assign(date, {type: 'date', required: true, value: payment.due_date || ''});
    date.dataset.field = 'due_date';
    date.setAttribute('aria-label', t('Payment date') + ' ' + (index + 1));
    row.append(label, amount, date);
    paymentRows.append(row);
  });
  paymentCount.value = rows.length;
  setInstallments(true);
}
installmentToggle.addEventListener('change', () => setInstallments(installmentToggle.checked));
document.getElementById('generate-payments').addEventListener('click', () => {
  const count = Number(paymentCount.value);
  const first = billForm.due_date.value;
  if (!Number.isInteger(count) || count < 1 || count > 120 || !first || !billForm.amount.value) {
    showMsg(saveMsg, t('Enter a payment amount, first date and 1–120 payments.'), false);
    return;
  }
  const [year, month, day] = first.split('-').map(Number);
  const rows = Array.from({length: count}, (_, i) => {
    const d = new Date(Date.UTC(year, month - 1 + i, 1));
    const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
    d.setUTCDate(Math.min(day, last));
    return {amount: billForm.amount.value, due_date: d.toISOString().slice(0, 10)};
  });
  renderPayments(rows);
});

let scanning = false;
let saving = false;
let previewUrl = null;
let suggestTimer = null;
let suggestionVersion = 0;

async function loadCategories() {
  try {
    const res = await apiGet("/api/categories");

    if (!res.ok) {
      throw new Error("Categories could not be loaded");
    }

    const previous = catSelect.value;
    catSelect.replaceChildren();

    for (const category of res.categories) {
      catSelect.add(new Option(categoryLabel(category), category));
    }

    if (res.categories.includes(previous)) {
      catSelect.value = previous;
    } else if (res.categories.includes("אחר")) {
      catSelect.value = "אחר";
    }

    return true;
  } catch (error) {
    showMsg(saveMsg, t("לא ניתן לטעון קטגוריות. נסו לרענן."), false);
    return false;
  }
}

const categoriesReady = loadCategories();

// Show or hide the recurrence period.
recToggle.addEventListener("change", () => {
  recPeriod.classList.toggle("hidden", !recToggle.checked);
});

recPeriod.classList.toggle("hidden", !recToggle.checked);

// Suggest a category from the supplier name.
billForm.supplier.addEventListener("input", () => {
  clearTimeout(suggestTimer);

  const version = ++suggestionVersion;
  const supplier = billForm.supplier.value.trim();

  catHint.textContent = "";
  if (!supplier) return;

  suggestTimer = setTimeout(async () => {
    try {
      const res = await apiGet(
        `/api/suggest-category?supplier=${encodeURIComponent(supplier)}`
      );

      await categoriesReady;

      if (version !== suggestionVersion) return;
      if (billForm.supplier.value.trim() !== supplier) return;

      if (res.ok && res.category) {
        const exists = Array.from(catSelect.options).some(
          option => option.value === res.category
        );

        if (exists) {
          catSelect.value = res.category;
          catHint.textContent =
            t("הקטגוריה {category} סומנה אוטומטית לפי שם הספק", {category: categoryLabel(res.category)});
        }
      }
    } catch (error) {
      if (version === suggestionVersion) {
        catHint.textContent = "";
      }
    }
  }, 250);
});

// Preview the selected image.
scanFile.addEventListener("change", () => {
  hiddenImage.value = "";
  scanMsg.textContent = "";

  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }

  const file = scanFile.files[0];

  if (!file) {
    preview.removeAttribute("src");
    previewWrap.classList.add("hidden");
    return;
  }

  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;
  previewWrap.classList.remove("hidden");
});

// Scan the image.
scanForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (scanning || saving) return;

  const file = scanFile.files[0];

  if (!file) {
    showMsg(scanMsg, t("בחרו תמונה לסריקה."), false);
    return;
  }

  scanning = true;
  scanFile.disabled = true;

  const scanButton = scanForm.querySelector(
    'button[type="submit"], button:not([type]), input[type="submit"]'
  );

  if (scanButton) scanButton.disabled = true;

  hiddenImage.value = "";
  // A new scan must not keep fields returned by a previous image.
  setInstallments(false);
  paymentRows.replaceChildren();
  paymentCount.value = 1;
  recToggle.checked = false;
  recPeriod.classList.add('hidden');
  billForm.supplier.value = "";
  billForm.amount.value = "";
  billForm.due_date.value = "";
  catHint.textContent = "";
  if (Array.from(catSelect.options).some(option => option.value === "אחר")) {
    catSelect.value = "אחר";
  }

  // Ignore any pending category suggestion.
  clearTimeout(suggestTimer);
  suggestionVersion++;

  showMsg(scanMsg, t("סורק... נא להמתין."), true);

  try {
    const formData = new FormData();
    formData.append("image", file);

    const response = await fetch("/api/bills/scan", {
      method: "POST",
      body: formData,
      credentials: "same-origin",
    });

    if (response.status === 401) {
      showMsg(scanMsg, t("יש להתחבר מחדש לפני הסריקה."), false);
      return;
    }

    if (response.status === 413) {
      showMsg(scanMsg, t("התמונה גדולה מדי. בחרו תמונה קטנה יותר."), false);
      return;
    }

    const res = await response.json();

    if (!response.ok || !res.ok) {
      showMsg(scanMsg, res.error || t("הסריקה נכשלה."), false);
      return;
    }

    if (res.image) {
      hiddenImage.value = res.image;
    }

    if (!res.ocr_available) {
      showMsg(
        scanMsg,
        t("התמונה נשמרה, אך מנוע הזיהוי אינו זמין. מלאו ידנית."),
        false
      );
      return;
    }

    if (res.ocr_error) {
      showMsg(
        scanMsg,
        res.ocr_error || t("לא ניתן לקרוא את התמונה. נסו שוב או מלאו ידנית."),
        false
      );
      return;
    }

    if (res.supplier) {
      billForm.supplier.value = res.supplier;
    }

    if (res.amount != null) {
      billForm.amount.value = res.amount;
    }

    const dateValue = typeof res.due_date === "string" ? res.due_date : "";
    billForm.due_date.value = /^\d{4}-\d{2}-\d{2}$/.test(dateValue)
      ? dateValue
      : "";

    if (Array.isArray(res.installments) && res.installments.length) renderPayments(res.installments);

    await categoriesReady;

    if (res.category) {
      const exists = Array.from(catSelect.options).some(
        option => option.value === res.category
      );

      if (exists) {
        catSelect.value = res.category;
        catHint.textContent =
          t("הקטגוריה {category} סומנה אוטומטית", {category: categoryLabel(res.category)});
      }
    }

    const complete = Boolean(
      res.supplier &&
      res.amount != null &&
      billForm.due_date.value
    );

    const scanNotice = typeof res.ocr_notice === "string" ? res.ocr_notice : "";
    showMsg(
      scanMsg,
      scanNotice || (complete
        ? t("הסריקה הסתיימה. בדקו ותקנו את הפרטים לפני השמירה.")
        : t("זוהו פרטים חלקיים. השדות שלא זוהו נשארו ריקים; השלימו ובדקו לפני השמירה.")),
      complete && !scanNotice
    );
  } catch (error) {
    showMsg(
      scanMsg,
      t("לא התקבלה תשובה תקינה מהשרת. נסו שוב."),
      false
    );
  } finally {
    scanning = false;
    scanFile.disabled = false;
    if (scanButton) scanButton.disabled = false;
  }
});

// Save the bill.
billForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (saving) return;

  if (scanning) {
    showMsg(saveMsg, t("המתינו לסיום הסריקה לפני השמירה."), false);
    return;
  }

  if (!billForm.reportValidity()) return;

  saving = true;

  const saveButton = billForm.querySelector(
    'button[type="submit"], button:not([type]), input[type="submit"]'
  );

  if (saveButton) saveButton.disabled = true;

  let saved = false;

  try {
    const data = formToObj(billForm);
    data.is_recurring = recToggle.checked;
    if (installmentToggle.checked) {
      const rows = [...paymentRows.querySelectorAll('.payment-row')];
      if (!rows.length || rows.length !== Number(paymentCount.value)) {
        showMsg(saveMsg, t('Build and review the payment schedule before saving.'), false);
        return;
      }
      data.installments = rows.map(row => ({
        amount: row.querySelector('[data-field="amount"]').value,
        due_date: row.querySelector('[data-field="due_date"]').value,
      }));
      data.amount = data.installments[0].amount;
      data.due_date = data.installments[0].due_date;
    }

    const res = await apiSend("/api/bills", "POST", data);

    if (!res.ok) {
      showMsg(saveMsg, res.error || t("השמירה נכשלה."), false);
      return;
    }

    saved = true;

    showMsg(
      saveMsg,
      t("החשבון נשמר! עובר לרשימת החשבונות..."),
      true
    );

    setTimeout(() => {
      window.location.href = "/bills";
    }, 800);
  } catch (error) {
    showMsg(
      saveMsg,
      t("לא התקבל אישור שמירה. בדקו ברשימת החשבונות לפני ניסיון נוסף."),
      false
    );
  } finally {
    if (!saved) {
      saving = false;
      if (saveButton) saveButton.disabled = false;
    }
  }
});