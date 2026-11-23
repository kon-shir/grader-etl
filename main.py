"""
Итоговый проект: API грейдера -> валидация -> PostgreSQL -> (Google Sheets, e-mail).

Примеры запуска:
    python main.py                                   # вчерашний день (UTC)
    python main.py --start 2026-05-31 --end 2026-06-01
    python main.py --start "2026-05-31 12:00:00" --end "2026-05-31 18:00:00" --no-email
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import config
from log_setup import setup_logging

log = logging.getLogger("main")


def parse_dt(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"неверный формат даты: {value!r}")


def parse_args():
    today_utc = datetime.now(timezone.utc).replace(tzinfo=None).replace(
        hour=0, minute=0, second=0, microsecond=0)
    p = argparse.ArgumentParser(description="Загрузка статистики грейдера в PostgreSQL")
    p.add_argument("--start", type=parse_dt, default=today_utc - timedelta(days=1),
                   help="начало периода, UTC (по умолчанию — начало вчерашнего дня)")
    p.add_argument("--end", type=parse_dt, default=today_utc,
                   help="конец периода, UTC, не включительно (по умолчанию — начало сегодняшнего дня)")
    p.add_argument("--no-sheets", action="store_true", help="не выгружать в Google Sheets")
    p.add_argument("--no-email", action="store_true", help="не отправлять письмо")
    args = p.parse_args()
    if args.start >= args.end:
        p.error("--start должен быть раньше --end")
    return args


def format_stats(stats: list[dict]) -> str:
    if not stats:
        return "Данных за период нет."
    lines = []
    for s in stats:
        lines.append(
            f"{s['day']}: попыток {s['attempts_total']} (run {s['runs']}, submit {s['submits']}), "
            f"верных submit {s['correct_submits']} ({s['success_rate_pct'] or 0}%), "
            f"уникальных юзеров {s['unique_users']}, задач {s['unique_tasks']}"
        )
    return "\n".join(lines)


def run(args, log_file) -> int:
    # импорты внутри, чтобы ошибки импорта тоже попали в лог
    import api_client
    import db
    import transform

    t0 = time.perf_counter()
    summary = {"downloaded": 0, "valid": 0, "skipped": 0, "inserted": 0, "failed_chunks": 0}
    stats: list[dict] = []
    errors: list[str] = []

    log.info("===== Запуск скрипта: период %s – %s (UTC) =====", args.start, args.end)
    try:
        records, summary["failed_chunks"] = api_client.fetch_period(args.start, args.end)
        summary["downloaded"] = len(records)
        if summary["failed_chunks"]:
            errors.append(f"не скачано интервалов: {summary['failed_chunks']}")

        attempts, summary["skipped"] = transform.transform(records)
        summary["valid"] = len(attempts)

        conn = db.connect()
        log.info("Подключение к PostgreSQL установлено (%s:%s/%s)",
                 config.DB_CONFIG["host"], config.DB_CONFIG["port"], config.DB_CONFIG["dbname"])
        try:
            db.ensure_schema(conn)
            if attempts:
                summary["inserted"] = db.load_attempts(conn, attempts)
            stats = db.daily_stats(conn, args.start, args.end)
        finally:
            conn.close()
    except Exception as exc:
        log.exception("Критическая ошибка: %s", exc)
        errors.append(f"критическая ошибка: {exc}")

    # --- доп. задание 1 ---
    if config.GSHEETS_ENABLED and not args.no_sheets and stats:
        try:
            import sheets
            sheets.upload_daily_stats(stats)
        except Exception as exc:
            log.exception("Ошибка выгрузки в Google Sheets: %s", exc)
            errors.append(f"Google Sheets: {exc}")

    elapsed = time.perf_counter() - t0
    status = "ОШИБКИ" if errors else "OK"
    report = (
        f"Статус: {status}\n"
        f"Период: {args.start} – {args.end} (UTC)\n"
        f"Скачано записей: {summary['downloaded']}\n"
        f"Валидных: {summary['valid']}, пропущено при валидации: {summary['skipped']}\n"
        f"Добавлено в БД: {summary['inserted']} (дубли не вставляются)\n"
        f"Время работы: {elapsed:.1f} с\n\n"
        f"Агрегаты по дням:\n{format_stats(stats)}\n"
        + (f"\nПроблемы:\n- " + "\n- ".join(errors) + "\n" if errors else "")
    )
    log.info("===== Итог =====\n%s", report)

    # --- доп. задание 2 ---
    if config.EMAIL_ENABLED and not args.no_email:
        try:
            import mailer
            mailer.send_report(f"[Grader ETL] {status}: {args.start:%Y-%m-%d} – {args.end:%Y-%m-%d}",
                               report, log_file)
        except Exception as exc:
            log.exception("Ошибка отправки письма: %s", exc)

    log.info("===== Скрипт завершён за %.1f с =====", elapsed)
    return 1 if errors else 0


def main():
    args = parse_args()
    log_file = setup_logging(config.LOG_DIR, config.LOG_KEEP_DAYS)
    sys.exit(run(args, log_file))


if __name__ == "__main__":
    main()
