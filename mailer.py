import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def send_email(to_addr, subject, body):
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_email = os.environ.get("MAIL_FROM", "").strip()

    if not api_key or not sender_email:
        print("[EMAIL ERROR] Missing BREVO_API_KEY or MAIL_FROM")
        return False

    payload = {
        "sender": {
            "name": "BillEase",
            "email": sender_email,
        },
        "to": [{"email": to_addr}],
        "subject": subject,
        "textContent": body,
    }

    req = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as response:
            accepted = response.status == 201
            if accepted:
                print("[EMAIL] Brevo accepted the message")
            return accepted
    except HTTPError as exc:
        print(f"[EMAIL ERROR] Brevo HTTP status: {exc.code}")
        return False
    except (URLError, TimeoutError, OSError):
        print("[EMAIL ERROR] Connection failed or timed out")
        return False
