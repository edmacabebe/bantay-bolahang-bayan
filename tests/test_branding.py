from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

from lotto_signal.pcso import USER_AGENT


ROOT = Path(__file__).parents[1]
OLD_REPOSITORY = "edmacabebe/pcso-lotto-signal-monitor"
NEW_REPOSITORY = "edmacabebe/bantay-bolahang-bayan"
ACTIVE_TEXT_SURFACES = (
    ROOT / "README.md",
    ROOT / "pyproject.toml",
    ROOT / "src/lotto_signal/pcso.py",
    ROOT / "codex/monitor-prompt.md",
    ROOT / "docs/operations.md",
    ROOT / "docs/superpowers/specs/2026-10-28-pcso-lotto-signal-monitor-design.md",
    ROOT / "docs/superpowers/plans/2026-10-28-pcso-lotto-signal-monitor.md",
)


def test_distribution_and_cli_expose_the_new_brand_without_breaking_command() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert metadata["project"]["name"] == "bantay-bolahang-bayan"
    assert metadata["project"]["scripts"] == {
        "lotto-signal": "lotto_signal.cli:main"
    }


def test_public_identity_surfaces_use_the_canonical_repository() -> None:
    assert (ROOT / "README.md").read_text().startswith(
        "# Bantay Bolahang Bayan\n"
    )
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/lotto-monitor.yml").read_text()
    )
    assert workflow["name"] == "Bantay Bolahang Bayan monitor"
    assert USER_AGENT == (
        "bantay-bolahang-bayan/0.1 "
        "(+https://github.com/edmacabebe/bantay-bolahang-bayan)"
    )
    for path in ACTIVE_TEXT_SURFACES:
        content = path.read_text()
        assert OLD_REPOSITORY not in content, path
    assert NEW_REPOSITORY in USER_AGENT
