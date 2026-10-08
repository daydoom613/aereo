"""Turning attribute values read from a file into values JSON can carry."""

from __future__ import annotations

import math
from datetime import date, datetime, time
from typing import Any

import numpy
import pandas


def to_json_safe(value: Any) -> Any:
    """Missing values become None, dates ISO 8601 text, NumPy scalars plain Python numbers."""
    if isinstance(value, list | tuple | numpy.ndarray):
        return [to_json_safe(item) for item in value]
    if value is None or pandas.isna(value):
        return None
    if isinstance(value, numpy.generic):
        value = value.item()
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, float) and not math.isfinite(value):
        return None  # JSON has no infinity
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)
