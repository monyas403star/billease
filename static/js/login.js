// login page
const form = document.getElementById("login-form");
const msg = document.getElementById("login-msg");

let loggingIn = false;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (loggingIn) return;

  loggingIn = true;
  showMsg(msg, "מתחבר...", true);

  try {
    const data = formToObj(form);
    const res = await apiSend("/api/login", "POST", data);

    if (!res.ok) {
      showMsg(msg, res.error || "ההתחברות נכשלה", false);
      return;
    }

    const profile = await apiGet("/api/profile");

    if (!profile.ok || !profile.user) {
      showMsg(msg, "לא ניתן לטעון את פרטי החשבון. נסו שוב.", false);
      return;
    }

    const isAdmin = profile.user.is_admin === true;

    showMsg(
      msg,
      isAdmin ? "מעבר למסך הניהול..." : "מעבר לחשבון שלך...",
      true
    );

    window.location.href = isAdmin ? "/admin" : "/dashboard";
  } catch (error) {
    showMsg(msg, "שגיאת תקשורת. נסו שוב.", false);
  } finally {
    loggingIn = false;
  }
});
