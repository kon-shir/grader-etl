"""Загрузка данных из API грейдера."""
import logging
import time
from datetime import datetime, timedelta
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

log = logging.getLogger("api")

API_DT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


class ApiError(Exception):
    pass


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,                      # 2, 4, 8 секунд между попытками
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def split_period(start: datetime, end: datetime, hours: int) -> Iterator[tuple[datetime, datetime]]:
    """Разбивает [start, end) на интервалы по `hours` часов."""
    step = timedelta(hours=hours)
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt


def fetch_chunk(session: requests.Session, start: datetime, end: datetime) -> list[dict]:
    params = {
        "client": config.API_CLIENT,
        "client_key": config.API_CLIENT_KEY,
        "start": start.strftime(API_DT_FORMAT),
        "end": end.strftime(API_DT_FORMAT),
    }
    try:
        resp = session.get(config.API_URL, params=params, timeout=config.API_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError(f"Сетевая ошибка при обращении к API: {exc}") from exc

    if resp.status_code != 200:
        raise ApiError(
            f"API вернул status_code={resp.status_code} для периода {start} – {end}: "
            f"{resp.text[:300]!r}"
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiError(f"Ответ API не является JSON: {resp.text[:300]!r}") from exc
    if not isinstance(data, list):
        raise ApiError(f"Ожидался список записей, получено: {type(data).__name__}")
    return data


def fetch_period(start: datetime, end: datetime) -> tuple[list[dict], int]:
    """Скачивает все записи за период. Возвращает (записи, число неудачных интервалов)."""
    if not config.API_CLIENT or not config.API_CLIENT_KEY:
        raise ApiError("Не заданы API_CLIENT / API_CLIENT_KEY — заполните их в файле .env")
    limit = datetime.strptime(config.API_DATA_LIMIT, "%Y-%m-%d")
    if end > limit:
        log.warning("Актуальные данные в API есть только до %s — конец периода (%s) позже", limit, end)

    log.info("Скачивание началось: период %s – %s, интервалы по %s ч",
             start, end, config.API_CHUNK_HOURS)
    t0 = time.perf_counter()
    session = _make_session()
    records: list[dict] = []
    failed_chunks = 0

    for chunk_start, chunk_end in split_period(start, end, config.API_CHUNK_HOURS):
        t_chunk = time.perf_counter()
        try:
            chunk = fetch_chunk(session, chunk_start, chunk_end)
        except ApiError as exc:
            failed_chunks += 1
            log.error(str(exc))
            continue
        records.extend(chunk)
        log.info("  %s – %s: получено %d записей за %.1f с",
                 chunk_start, chunk_end, len(chunk), time.perf_counter() - t_chunk)

    log.info("Скачивание завершилось: всего %d записей, ошибок интервалов: %d, время %.1f с",
             len(records), failed_chunks, time.perf_counter() - t0)
    return records, failed_chunks
