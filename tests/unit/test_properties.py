import json
from datetime import date, datetime

import numpy
import pandas
import pytest

from app.readers.properties import to_json_safe


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("text", "text"),
        (7, 7),
        (2.5, 2.5),
        (True, True),
        (None, None),
        (float("nan"), None),
        (float("inf"), None),
        (pandas.NaT, None),
        (pandas.NA, None),
        (numpy.int64(7), 7),
        (numpy.float64(2.5), 2.5),
        (numpy.bool_(True), True),
        (date(2026, 1, 15), "2026-01-15"),
        (datetime(2026, 1, 15, 9, 30), "2026-01-15T09:30:00"),
        (pandas.Timestamp("2026-01-15 09:30"), "2026-01-15T09:30:00"),
        (b"caf\xc3\xa9", "café"),
        ([numpy.int64(1), float("nan")], [1, None]),
        (numpy.array([1, 2]), [1, 2]),
    ],
)
def test_to_json_safe(value, expected):
    converted = to_json_safe(value)

    assert converted == expected
    assert type(converted) is type(expected)
    json.dumps(converted)


def test_unknown_types_become_text():
    assert to_json_safe(complex(1, 2)) == "(1+2j)"
