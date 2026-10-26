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
  if (form.preferred_language) form.preferred_language.value = res.user.preferred_language || "he";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = formToObj(form);
  delete data.user_id;
  const res = await apiSend("/api/profile", "PUT", data);
  if (res.ok) {
    showMsg(msg, t("נשמר!"), true);
    form.password.value = "";
    if (res.language && res.language !== uiSettings.locale) window.location.reload();
  } else {
    showMsg(msg, res.error || t("השמירה נכשלה"), false);
  }
});

loadProfile();
