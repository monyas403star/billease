// recover password page
const step1 = document.getElementById("otp-request");
const step2 = document.getElementById("otp-reset");
const msg1 = document.getElementById("step1-msg");
const msg2 = document.getElementById("step2-msg");

step1.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(step1);
  const res = await apiSend("/api/recover/request", "POST", data);
  if (res.ok) {
    showMsg(msg1, res.msg || "הקוד נשלח", true);
    step2.querySelector('input[name="user_id"]').value = data.user_id;
    step2.classList.remove("hidden");
  } else {
    showMsg(msg1, res.error || "השליחה נכשלה", false);
  }
});

step2.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(step2);
  const res = await apiSend("/api/recover/reset", "POST", data);
  if (res.ok) {
    showMsg(msg2, "הסיסמה עודכנה! מעבר להתחברות...", true);
    setTimeout(() => { window.location.href = "/"; }, 1200);
  } else {
    showMsg(msg2, res.error || "האיפוס נכשל", false);
  }
});
