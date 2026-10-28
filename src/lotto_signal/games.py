from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GameSpec:
    code: str
    name: str
    max_number: int
    draw_weekdays: frozenset[int]


GAMES: Mapping[str, GameSpec] = MappingProxyType(
    {
        "LOTTO42": GameSpec("LOTTO42", "Lotto 6/42", 42, frozenset({1, 3, 5})),
        "ML45": GameSpec("ML45", "Mega Lotto 6/45", 45, frozenset({0, 2, 4})),
        "SL49": GameSpec("SL49", "Super Lotto 6/49", 49, frozenset({1, 3, 6})),
        "GL55": GameSpec("GL55", "Grand Lotto 6/55", 55, frozenset({0, 2, 5})),
        "UL58": GameSpec("UL58", "Ultra Lotto 6/58", 58, frozenset({1, 4, 6})),
    }
)

# Add only PCSO-documented exceptional draw dates, with a source citation in the
# commit that introduces each date. Empty by default: ordinary weekday rules apply.
DRAW_DATE_EXCEPTIONS: Mapping[str, frozenset[date]] = MappingProxyType(
    {code: frozenset() for code in GAMES}
)
