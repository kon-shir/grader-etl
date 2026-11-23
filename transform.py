"""Разбор passback_params и валидация записей."""
import ast
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

log = logging.getLogger("transform")

PASSBACK_KEYS = ("oauth_consumer_key", "lis_result_sourcedid", "lis_outcome_service_url")
ATTEMPT_TYPES = {"run", "submit"}
DT_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S")


class ValidationError(ValueError):
    pass


@dataclass
class Attempt:
    user_id: str
    oauth_consumer_key: Optional[str]
    lis_result_sourcedid: Optional[str]
    lis_outcome_service_url: Optional[str]
    is_correct: Optional[bool]
    attempt_type: str
    created_at: datetime

    def record_hash(self) -> str:
        key = "|".join([self.user_id, self.lis_result_sourcedid or "", self.attempt_type,
                        self.created_at.isoformat()])
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def as_tuple(self) -> tuple:
        return (self.user_id, self.oauth_consumer_key, self.lis_result_sourcedid,
                self.lis_outcome_service_url, self.is_correct, self.attempt_type, self.created_at)


def parse_passback_params(raw) -> dict:
    """passback_params приходит как строковое представление python-dict (одинарные кавычки).
    Безопасно разбираем через ast.literal_eval (не eval!), с запасным вариантом через JSON.
    Лишние ключи отбрасываем, отсутствующие заполняем None."""
    if raw is None or raw == "":
        parsed = {}
    elif isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            try:
                parsed = json.loads(raw)
            except ValueError as exc:
                raise ValidationError(f"не удалось разобрать passback_params: {raw[:100]!r}") from exc
    else:
        raise ValidationError(f"passback_params неожиданного типа {type(raw).__name__}")

    if not isinstance(parsed, dict):
        raise ValidationError(f"passback_params не является словарём: {type(parsed).__name__}")

    result = {}
    for key in PASSBACK_KEYS:
        value = parsed.get(key)
        if value is not None and not isinstance(value, str):
            raise ValidationError(f"{key} должен быть строкой, получено {type(value).__name__}")
        result[key] = (value.strip() or None) if isinstance(value, str) else None
    return result


def _parse_dt(value) -> datetime:
    if not isinstance(value, str):
        raise ValidationError(f"created_at должен быть строкой, получено {value!r}")
    for fmt in DT_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            pass
    raise ValidationError(f"created_at в неизвестном формате: {value!r}")


def _parse_is_correct(value, attempt_type: str) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        result = value
    elif isinstance(value, int) and value in (0, 1):
        result = bool(value)
    elif isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0"}:
        result = value.strip().lower() in {"true", "1"}
    else:
        raise ValidationError(f"is_correct имеет недопустимое значение {value!r}")
    if attempt_type == "run":
        raise ValidationError(f"у попытки run is_correct должен быть null, получено {value!r}")
    return result


def validate_record(rec: dict) -> Attempt:
    if not isinstance(rec, dict):
        raise ValidationError(f"запись не является объектом: {rec!r}")

    user_id = rec.get("lti_user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValidationError(f"пустой или некорректный lti_user_id: {user_id!r}")

    attempt_type = rec.get("attempt_type")
    if attempt_type not in ATTEMPT_TYPES:
        raise ValidationError(f"недопустимый attempt_type: {attempt_type!r}")

    passback = parse_passback_params(rec.get("passback_params"))
    url = passback["lis_outcome_service_url"]
    if url is not None and not url.startswith(("http://", "https://")):
        raise ValidationError(f"lis_outcome_service_url не похож на URL: {url!r}")

    return Attempt(
        user_id=user_id.strip(),
        oauth_consumer_key=passback["oauth_consumer_key"],
        lis_result_sourcedid=passback["lis_result_sourcedid"],
        lis_outcome_service_url=url,
        is_correct=_parse_is_correct(rec.get("is_correct"), attempt_type),
        attempt_type=attempt_type,
        created_at=_parse_dt(rec.get("created_at")),
    )


def transform(records: list[dict]) -> tuple[list[Attempt], int]:
    """Возвращает (валидные записи, число пропущенных)."""
    log.info("Обработка данных началась: %d записей", len(records))
    valid: list[Attempt] = []
    skipped = 0
    for i, rec in enumerate(records):
        try:
            valid.append(validate_record(rec))
        except ValidationError as exc:
            skipped += 1
            log.warning("Запись #%d пропущена: %s", i, exc)
    log.info("Обработка данных завершилась: валидных %d, пропущено %d", len(valid), skipped)
    return valid, skipped
