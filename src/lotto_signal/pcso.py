from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from .domain import DrawRecord
from .games import GAMES


DEFAULT_BASE_URL = "https://lottomatik.pcso.gov.ph/api/backend"
USER_AGENT = "pcso-lotto-signal-monitor/0.1 (+https://github.com/edmacabebe/pcso-lotto-signal-monitor)"


class PcsoSourceError(RuntimeError):
    """Raised when official PCSO data cannot be retrieved or validated."""


@dataclass(frozen=True, slots=True)
class HistoryPage:
    page: int
    per_page: int
    total: int
    total_pages: int
    items: tuple[DrawRecord, ...]


class PcsoClient:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str = DEFAULT_BASE_URL,
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 0.25,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    def _get_json(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> tuple[Any, str]:
        url = f"{self._base_url}{path}"
        timeout = httpx.Timeout(15.0, connect=5.0)
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.get(
                    url,
                    params=params,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                    timeout=timeout,
                )
            except httpx.TransportError as exc:
                if attempt == self._max_attempts:
                    raise PcsoSourceError(f"PCSO transport failure: {exc}") from exc
            else:
                if response.status_code < 400:
                    try:
                        return response.json(), str(response.request.url)
                    except ValueError as exc:
                        raise PcsoSourceError("PCSO returned invalid JSON") from exc
                if response.status_code != 429 and response.status_code < 500:
                    raise PcsoSourceError(
                        f"PCSO request failed with HTTP {response.status_code}"
                    )
                if attempt == self._max_attempts:
                    raise PcsoSourceError(
                        f"PCSO request failed with HTTP {response.status_code}"
                    )
            if self._backoff_seconds:
                time.sleep(self._backoff_seconds * attempt)
        raise AssertionError("retry loop exhausted unexpectedly")

    def fetch_latest(self, retrieved_at: datetime) -> tuple[DrawRecord, ...]:
        payload, source_url = self._get_json("/get-results")
        if not isinstance(payload, list):
            raise PcsoSourceError("unexpected PCSO latest-results structure")
        draws: list[DrawRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                raise PcsoSourceError("unexpected PCSO result item")
            game_code = item.get("lottery")
            if game_code not in GAMES:
                continue
            draws.append(
                self._normalize_draw(item, str(game_code), retrieved_at, source_url)
            )
        return tuple(draws)

    def fetch_history_page(
        self,
        game_code: str,
        page: int,
        per_page: int,
        retrieved_at: datetime,
    ) -> HistoryPage:
        if game_code not in GAMES:
            raise ValueError(f"unknown game: {game_code}")
        payload, source_url = self._get_json(
            "/get-game-history",
            {"lottery": game_code, "page": page, "perPage": per_page},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise PcsoSourceError("unexpected PCSO history structure")
        try:
            items = tuple(
                self._normalize_draw(item, game_code, retrieved_at, source_url)
                for item in payload["items"]
            )
            return HistoryPage(
                page=int(payload["page"]),
                per_page=int(payload["perPage"]),
                total=int(payload["total"]),
                total_pages=int(payload["totalPages"]),
                items=items,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, PcsoSourceError):
                raise
            raise PcsoSourceError(f"invalid PCSO history page: {exc}") from exc

    def iter_history(
        self,
        game_code: str,
        retrieved_at: datetime,
        per_page: int = 100,
    ) -> Iterator[DrawRecord]:
        page_number = 1
        while True:
            page = self.fetch_history_page(
                game_code, page_number, per_page, retrieved_at
            )
            yield from page.items
            if page_number >= page.total_pages:
                return
            page_number += 1

    @staticmethod
    def _normalize_draw(
        payload: dict[str, Any],
        game_code: str,
        retrieved_at: datetime,
        source_url: str,
    ) -> DrawRecord:
        try:
            draw_id = str(payload["id"])
            if not draw_id.startswith(f"{game_code}S"):
                raise ValueError(
                    f"draw ID {draw_id!r} does not match requested game {game_code}"
                )
            draw_time = str(payload["drawTime"])
            if draw_time.endswith("+08"):
                draw_time = f"{draw_time}:00"
            return DrawRecord(
                draw_id=draw_id,
                game_code=game_code,
                draw_date=date.fromisoformat(str(payload["drawDate"])),
                draw_time=draw_time,
                published_numbers=tuple(int(value) for value in payload["result"]),
                jackpot=format(Decimal(str(payload["jackpot"])), "f"),
                total_winners=int(payload["totalWinners"]),
                retrieved_at=retrieved_at,
                source_url=source_url,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise PcsoSourceError(f"invalid PCSO draw: {exc}") from exc
