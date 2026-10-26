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