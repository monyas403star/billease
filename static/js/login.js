// login page
const form = document.getElementById("login-form");
const msg = document.getElementById("login-msg");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(form);
  showMsg(msg, "מתחבר...", true);
  const res = await apiSend("/api/login", "POST", data);
  if (res.ok) {
    showMsg(msg, "התחברת! טוען דשבורד...", true);
    window.location.href = "/dashboard";
  } else {
    showMsg(msg, res.error || "ההתחברות נכשלה", false);
  }
});
