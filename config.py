# Database settings - SQLite local configuration
DB_PATH = "database.db"

# Flask secret for sessions
SECRET_KEY = "billease-local-secret-change-me"

# Uploads folder for bill images
UPLOAD_DIR = "uploads"

# How many days before due date to send a reminder
REMINDER_DAYS = 2

# Email settings (optional, leave empty to print OTPs to console)
SMTP_HOST = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASS = ""
SMTP_FROM = "billease@local.test"