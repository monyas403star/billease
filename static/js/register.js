// register page
const form = document.getElementById("register-form");
const msg = document.getElementById("reg-msg");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(form);
  const res = await apiSend("/api/register", "POST", data);
  if (res.ok) {
    showMsg(msg, t("החשבון נפתח! מעבר ללוח הבקרה..."), true);
    setTimeout(() => {
      window.location.href = res.redirect || "/dashboard";
    }, 1200);
  } else {
    showMsg(msg, res.error || t("ההרשמה נכשלה"), false);
  }
});
