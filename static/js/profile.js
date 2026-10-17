// profile page
const form = document.getElementById("profile-form");
const msg = document.getElementById("profile-msg");

async function loadProfile() {
  const res = await apiGet("/api/profile");
  if (!res.ok) return;
  form.user_id.value = res.user.user_id;
  form.full_name.value = res.user.full_name || "";
  form.email.value = res.user.email || "";
  form.phone.value = res.user.phone || "";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(form);
  delete data.user_id;
  const res = await apiSend("/api/profile", "PUT", data);
  if (res.ok) {
    showMsg(msg, "נשמר!", true);
    form.password.value = "";
  } else {
    showMsg(msg, res.error || "השמירה נכשלה", false);
  }
});

loadProfile();
