"""Доп. задание 1: выгрузка дневных агрегатов в Google Sheets (через сервисный аккаунт)."""
import logging
from decimal import Decimal

import config

log = logging.getLogger("sheets")

COLUMNS = [
    ("day", "Дата (UTC)"),
    ("attempts_total", "Всего попыток"),
    ("runs", "Run"),
    ("submits", "Submit"),
    ("correct_submits", "Верных submit"),
    ("success_rate_pct", "Доля верных submit, %"),
    ("unique_users", "Уникальных юзеров"),
    ("unique_tasks", "Уникальных задач"),
    ("users_with_correct", "Юзеров с верным решением"),
    ("attempts_per_user", "Попыток на юзера"),
    ("peak_hour_utc", "Пиковый час (UTC)"),
]


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def upload_daily_stats(stats: list[dict]) -> None:
    """Пишет строки в лист; если строка за этот день уже есть — перезаписывает её."""
    import gspread  # импорт здесь, чтобы основной скрипт работал и без gspread

    if not stats:
        log.info("Нет агрегатов для выгрузки в Google Sheets")
        return

    log.info("Выгрузка в Google Sheets началась")
    gc = gspread.service_account(filename=str(config.GSHEETS_CREDENTIALS))
    sh = gc.open_by_key(config.GSHEETS_SPREADSHEET)
    try:
        ws = sh.worksheet(config.GSHEETS_WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=config.GSHEETS_WORKSHEET, rows=1000, cols=len(COLUMNS))
        log.info("Создан лист %s", config.GSHEETS_WORKSHEET)

    header = [title for _, title in COLUMNS]
    if ws.row_values(1) != header:
        ws.update(range_name="A1", values=[header])

    existing_days = ws.col_values(1)  # включая заголовок
    updated, appended = 0, 0
    for row in stats:
        values = [_cell(row.get(key)) for key, _ in COLUMNS]
        day = values[0]
        if day in existing_days:
            row_idx = existing_days.index(day) + 1
            ws.update(range_name=f"A{row_idx}", values=[values], value_input_option="USER_ENTERED")
            updated += 1
        else:
            ws.append_row(values, value_input_option="USER_ENTERED")
            existing_days.append(day)
            appended += 1
    log.info("Выгрузка в Google Sheets завершилась: добавлено %d строк, обновлено %d", appended, updated)
