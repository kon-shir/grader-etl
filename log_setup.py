"""Настройка логирования: файл logs/YYYY-MM-DD.log + вывод в консоль, ротация за N дней."""
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

LOG_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.log$")


def cleanup_old_logs(log_dir: Path, keep_days: int) -> list[str]:
    """Удаляет логи старше keep_days дней (сегодня + keep_days-1 предыдущих остаются)."""
    oldest_allowed = date.today() - timedelta(days=keep_days - 1)
    removed = []
    for path in log_dir.glob("*.log"):
        m = LOG_NAME_RE.match(path.name)
        if not m:
            continue
        try:
            log_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if log_date < oldest_allowed:
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def setup_logging(log_dir: Path, keep_days: int = 3) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{date.today():%Y-%m-%d}.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    # сторонние библиотеки слишком болтливы на уровне DEBUG/INFO
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    removed = cleanup_old_logs(log_dir, keep_days)
    log = logging.getLogger("logs")
    if removed:
        log.info("Удалены старые логи: %s", ", ".join(sorted(removed)))
    log.info("Лог пишется в %s", log_file)
    return log_file
