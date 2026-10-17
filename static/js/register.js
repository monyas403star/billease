// register page
const form = document.getElementById("register-form");
const msg = document.getElementById("reg-msg");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(form);
  const res = await apiSend("/api/register", "POST", data);
  if (res.ok) {
    showMsg(msg, "החשבון נפתח! מעבר להתחברות...", true);
    setTimeout(() => { window.location.href = "/"; }, 1200);
  } else {
    showMsg(msg, res.error || "ההרשמה נכשלה", false);
  }
});
