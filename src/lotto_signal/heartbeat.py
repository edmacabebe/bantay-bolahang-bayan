from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


MODES = frozenset({"morning", "evening"})


def operational_date(mode: str, now: datetime) -> date:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("heartbeat time must be timezone-aware")
    if mode not in MODES:
        raise ValueError(f"unsupported heartbeat mode: {mode}")
    if mode == "evening" and now.hour < 12:
        return now.date() - timedelta(days=1)
    return now.date()


def _load(root: Path) -> dict[str, Any]:
    path = root / "state" / "heartbeats.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def record_heartbeat(
    root: Path,
    mode: str,
    now: datetime,
    status: str,
) -> None:
    day = operational_date(mode, now)
    payload = _load(root)
    payload[mode] = {
        "operational_date": day.isoformat(),
        "finished_at": now.isoformat(),
        "status": status,
    }
    path = root / "state" / "heartbeats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}\n"
    )
    temporary.replace(path)


def heartbeat_matches(root: Path, mode: str, expected_date: date) -> bool:
    if mode not in MODES:
        raise ValueError(f"unsupported heartbeat mode: {mode}")
    entry = _load(root).get(mode)
    return bool(
        isinstance(entry, dict)
        and entry.get("operational_date") == expected_date.isoformat()
    )
