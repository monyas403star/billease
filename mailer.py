# sends email if SMTP is set, else prints to console
import smtplib
from email.mime.text import MIMEText
import config


def send_email(to_addr, subject, body):
    if not config.SMTP_HOST:
        # no smtp set, print so we can still test
        print(f"[EMAIL to {to_addr}] {subject}\n{body}\n")
        return True
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = config.SMTP_FROM
        msg["To"] = to_addr
        s = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT)
        s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASS)
        s.sendmail(config.SMTP_FROM, [to_addr], msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False
