import os
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()

# =========================================
# NEXRA EDUCATION CONFIGURATION
# =========================================

GMAIL_EMAIL = os.getenv(
    "GMAIL_EMAIL",
    "nexra.education@gmail.com"
)

GMAIL_APP_PASSWORD = os.getenv(
    "GMAIL_APP_PASSWORD",
    ""
)

FLASK_SECRET_KEY = os.getenv(
    "FLASK_SECRET_KEY",
    "nexra-development-secret-change-later"
)