"""Path and time-prefix helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping
from urllib.parse import quote


def encode_segment(segment: object) -> str:
    return quote(str(segment), safe="")


def path_key(path: Iterable[object]) -> str:
    segments = list(path)
    if not segments:
        return "/"
    return "/" + "/".join(encode_segment(segment) for segment in segments)


def prefix_keys(path: Iterable[object]) -> list[str]:
    segments = list(path)
    return [path_key(segments[: index + 1]) for index in range(len(segments))]


def parse_utc_time(iso_time: str) -> dict[str, int | str]:
    parsed = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
    return {
        "iso": parsed.isoformat().replace("+00:00", "Z"),
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
        "hour": parsed.hour,
        "minute": parsed.minute,
        "second": parsed.second,
    }


def time_prefix_keys(time_parts: Mapping[str, int | str]) -> list[str]:
    return [
        f"/{int(time_parts['year']):04d}",
        f"/{int(time_parts['year']):04d}/{int(time_parts['month']):02d}",
        (
            f"/{int(time_parts['year']):04d}/{int(time_parts['month']):02d}"
            f"/{int(time_parts['day']):02d}"
        ),
        (
            f"/{int(time_parts['year']):04d}/{int(time_parts['month']):02d}"
            f"/{int(time_parts['day']):02d}/{int(time_parts['hour']):02d}"
        ),
    ]


def hour_shard_path(time_parts: Mapping[str, int | str]) -> str:
    return time_prefix_keys(time_parts)[-1]
