"""Работа с PostgreSQL: создание таблицы, загрузка, агрегаты."""
import logging
import time
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import config
from transform import Attempt

log = logging.getLogger("db")

DDL = """
CREATE TABLE IF NOT EXISTS grader_attempts (
    id                      BIGSERIAL PRIMARY KEY,
    user_id                 TEXT        NOT NULL,
    oauth_consumer_key      TEXT,
    lis_result_sourcedid    TEXT,
    lis_outcome_service_url TEXT,
    is_correct              BOOLEAN,
    attempt_type            TEXT        NOT NULL CHECK (attempt_type IN ('run', 'submit')),
    created_at              TIMESTAMP   NOT NULL,
    loaded_at               TIMESTAMP   NOT NULL DEFAULT now(),
    -- md5 ключевых полей: защита от дублей при повторном запуске за тот же период
    record_hash             TEXT        NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_grader_attempts_created_at ON grader_attempts (created_at);
CREATE INDEX IF NOT EXISTS idx_grader_attempts_user_id    ON grader_attempts (user_id);
"""

INSERT_SQL = """
INSERT INTO grader_attempts
    (user_id, oauth_consumer_key, lis_result_sourcedid, lis_outcome_service_url,
     is_correct, attempt_type, created_at, record_hash)
VALUES %s
ON CONFLICT (record_hash) DO NOTHING
RETURNING id
"""

DAILY_STATS_SQL = """
SELECT
    created_at::date                                              AS day,
    count(*)                                                      AS attempts_total,
    count(*) FILTER (WHERE attempt_type = 'run')                  AS runs,
    count(*) FILTER (WHERE attempt_type = 'submit')               AS submits,
    count(*) FILTER (WHERE is_correct)                            AS correct_submits,
    round(100.0 * count(*) FILTER (WHERE is_correct)
          / nullif(count(*) FILTER (WHERE attempt_type = 'submit'), 0), 2) AS success_rate_pct,
    count(DISTINCT user_id)                                       AS unique_users,
    count(DISTINCT lis_result_sourcedid)                          AS unique_tasks,
    count(DISTINCT user_id) FILTER (WHERE is_correct)             AS users_with_correct,
    round(count(*)::numeric / nullif(count(DISTINCT user_id), 0), 2) AS attempts_per_user,
    extract(hour FROM mode() WITHIN GROUP (ORDER BY date_trunc('hour', created_at)))::int
                                                                  AS peak_hour_utc
FROM grader_attempts
WHERE created_at >= %s AND created_at < %s
GROUP BY day
ORDER BY day
"""


def connect():
    return psycopg2.connect(**config.DB_CONFIG)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    log.info("Таблица grader_attempts готова")


def load_attempts(conn, attempts: list[Attempt]) -> int:
    """Загружает записи пачками. Возвращает число реально вставленных (без дублей)."""
    log.info("Заполнение базы началось: %d записей, пачки по %d", len(attempts), config.DB_BATCH_SIZE)
    t0 = time.perf_counter()
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(attempts), config.DB_BATCH_SIZE):
            batch = [a.as_tuple() + (a.record_hash(),) for a in attempts[i:i + config.DB_BATCH_SIZE]]
            rows = execute_values(cur, INSERT_SQL, batch, page_size=len(batch), fetch=True)
            inserted += len(rows)
    conn.commit()
    log.info("Заполнение базы завершилось: вставлено %d, дублей пропущено %d, время %.1f с",
             inserted, len(attempts) - inserted, time.perf_counter() - t0)
    return inserted


def daily_stats(conn, start: datetime, end: datetime) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(DAILY_STATS_SQL, (start, end))
        rows = [dict(r) for r in cur.fetchall()]
    log.info("Посчитаны агрегаты за %d дн.", len(rows))
    return rows
