"""Настройки проекта. Все секреты читаются из переменных окружения / файла .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- API ---------------------------------------------------------------------
API_URL = os.getenv("API_URL", "https://api.itresume.ru/statistics/")
API_CLIENT = os.getenv("API_CLIENT", "Skillfactory")
API_CLIENT_KEY = os.getenv("API_CLIENT_KEY", "")  # ключ из задания — только в .env
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "120"))          # секунд на один запрос
API_CHUNK_HOURS = int(os.getenv("API_CHUNK_HOURS", "6"))    # период разбивается на куски
API_DATA_LIMIT = os.getenv("API_DATA_LIMIT", "2026-06-01")  # актуальные данные только до этой даты

# --- PostgreSQL --------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "grader"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}
DB_BATCH_SIZE = int(os.getenv("DB_BATCH_SIZE", "1000"))

# --- Логи --------------------------------------------------------------------
LOG_DIR = BASE_DIR / os.getenv("LOG_DIR", "logs")
LOG_KEEP_DAYS = int(os.getenv("LOG_KEEP_DAYS", "3"))

# --- Google Sheets (доп. задание 1) -----------------------------------------
GSHEETS_ENABLED = _bool("GSHEETS_ENABLED")
GSHEETS_CREDENTIALS = BASE_DIR / os.getenv("GSHEETS_CREDENTIALS", "credentials.json")
GSHEETS_SPREADSHEET = os.getenv("GSHEETS_SPREADSHEET", "")   # ключ таблицы из URL
GSHEETS_WORKSHEET = os.getenv("GSHEETS_WORKSHEET", "daily_stats")

# --- Почта (доп. задание 2) --------------------------------------------------
EMAIL_ENABLED = _bool("EMAIL_ENABLED")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.mail.ru")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")   # пароль для внешних приложений mail.ru
EMAIL_RECIPIENTS = [e.strip() for e in os.getenv("EMAIL_RECIPIENTS", "").split(",") if e.strip()]
EMAIL_ATTACH_LOG = _bool("EMAIL_ATTACH_LOG", True)
