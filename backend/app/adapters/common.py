from pathlib import Path

import pandas as pd


class AdapterError(ValueError):
    pass


def read_csv(path: str | Path, required_columns: set[str]) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    missing = sorted(required_columns - set(df.columns))
    if missing:
        raise AdapterError(f"Missing required columns: {missing}")
    return df


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def parse_datetime(value: object):
    timestamp = pd.to_datetime(value, errors="raise")
    if timestamp.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return timestamp.to_pydatetime()


def parse_optional_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
