from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from lotto_signal.pcso import PcsoClient, PcsoSourceError


FIXTURES = Path(__file__).parent / "fixtures" / "pcso"
RETRIEVED_AT = datetime(2026, 10, 17, 0, 30, tzinfo=timezone.utc)


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


def client_for(handler: httpx.MockTransport) -> PcsoClient:
    return PcsoClient(
        httpx.Client(transport=handler),
        max_attempts=3,
        backoff_seconds=0,
    )


def test_fetch_latest_normalizes_only_supported_six_number_games() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/backend/get-results"
        assert request.headers["User-Agent"].startswith("pcso-lotto-signal-monitor/")
        return httpx.Response(200, json=fixture("latest.json"))

    draws = client_for(httpx.MockTransport(handler)).fetch_latest(RETRIEVED_AT)

    assert [draw.game_code for draw in draws] == ["LOTTO42", "ML45"]
    assert draws[0].published_numbers == (28, 36, 11, 17, 35, 14)
    assert draws[0].draw_time == "21:00:00+08:00"
    assert draws[1].jackpot == "110527091.63"


def test_history_uses_requested_game_when_payload_lottery_contains_draw_id() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=fixture("history_page.json"))
    )

    page = client_for(transport).fetch_history_page(
        "LOTTO42", page=1, per_page=2, retrieved_at=RETRIEVED_AT
    )

    assert page.total_pages == 2
    assert [draw.game_code for draw in page.items] == ["LOTTO42", "LOTTO42"]
    assert page.items[0].draw_id == "LOTTO42S0000299"


def test_history_accepts_official_legacy_ids_but_rejects_cross_game_ids() -> None:
    payload = fixture("history_page.json")
    assert isinstance(payload, dict)
    payload["items"][0]["id"] = "LOTTO42LOTTO42S0000001"
    payload["items"][1]["id"] = "LOTTO429550700"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    page = client_for(transport).fetch_history_page(
        "LOTTO42", page=1, per_page=2, retrieved_at=RETRIEVED_AT
    )

    assert [draw.draw_id for draw in page.items] == [
        "LOTTO42LOTTO42S0000001",
        "LOTTO429550700",
    ]

    payload["items"][0]["id"] = "ML45S0000001"
    with pytest.raises(PcsoSourceError, match="does not match requested game"):
        client_for(transport).fetch_history_page(
            "LOTTO42", page=1, per_page=2, retrieved_at=RETRIEVED_AT
        )


def test_iter_history_stops_at_reported_total_pages() -> None:
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(request.url.params["page"])
        requested_pages.append(page_number)
        payload = fixture("history_page.json")
        assert isinstance(payload, dict)
        if page_number == 2:
            payload = {
                **payload,
                "page": 2,
                "items": [
                    {
                        **payload["items"][0],
                        "id": "LOTTO42S0000297",
                        "lottery": "LOTTO42S0000297",
                        "drawDate": "2026-10-10",
                    }
                ],
            }
        return httpx.Response(200, json=payload)

    draws = tuple(
        client_for(httpx.MockTransport(handler)).iter_history(
            "LOTTO42", RETRIEVED_AT, per_page=2
        )
    )

    assert requested_pages == [1, 2]
    assert [draw.draw_id for draw in draws] == [
        "LOTTO42S0000299",
        "LOTTO42S0000298",
        "LOTTO42S0000297",
    ]


def test_transient_error_retries_but_permanent_error_does_not() -> None:
    attempts = 0

    def transient(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=fixture("latest.json"))

    draws = client_for(httpx.MockTransport(transient)).fetch_latest(RETRIEVED_AT)
    assert len(draws) == 2
    assert attempts == 3

    permanent_attempts = 0

    def permanent(request: httpx.Request) -> httpx.Response:
        nonlocal permanent_attempts
        permanent_attempts += 1
        return httpx.Response(404, json={"error": "missing"})

    with pytest.raises(PcsoSourceError, match="404"):
        client_for(httpx.MockTransport(permanent)).fetch_latest(RETRIEVED_AT)
    assert permanent_attempts == 1


def test_malformed_history_result_is_rejected() -> None:
    payload = fixture("history_page.json")
    assert isinstance(payload, dict)
    payload["items"][0]["result"] = ["01", "02", "03", "04", "05", "05"]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    with pytest.raises(PcsoSourceError, match="invalid PCSO draw"):
        client_for(transport).fetch_history_page(
            "LOTTO42", page=1, per_page=2, retrieved_at=RETRIEVED_AT
        )
