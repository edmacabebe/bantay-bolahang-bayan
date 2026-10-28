from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/lotto-monitor.yml"
COMMIT_SCRIPT = ROOT / "scripts/commit-state.sh"


def load_workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_cloud_workflow_has_safe_runner_permissions_and_concurrency() -> None:
    workflow = load_workflow()

    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    job = workflow["jobs"]["monitor"]
    assert job["runs-on"] == "ubuntu-latest"
    assert "secrets" not in WORKFLOW.read_text().lower()


def test_cloud_workflow_has_manila_schedules_and_manual_modes() -> None:
    workflow = load_workflow()
    triggers = workflow["on"]

    schedules = triggers["schedule"]
    assert {(item["cron"], item["timezone"]) for item in schedules} == {
        ("17 22 * * *", "Asia/Manila"),
        ("17 7 * * *", "Asia/Manila"),
    }
    mode = triggers["workflow_dispatch"]["inputs"]["mode"]
    assert mode["type"] == "choice"
    assert mode["options"] == ["morning", "evening", "audit", "backfill"]


def test_tests_run_before_monitor_with_python_312_and_state_commit_last() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["monitor"]["steps"]
    names = [step["name"] for step in steps]

    setup = next(step for step in steps if step["name"] == "Set up Python")
    checkout = next(step for step in steps if step["name"] == "Check out repository")
    assert checkout["uses"] == "actions/checkout@v7"
    assert setup["uses"] == "actions/setup-python@v7"
    assert setup["with"]["python-version"] == "3.12"
    assert names.index("Run tests") < names.index("Run monitor")
    assert names[-1] == "Commit auditable state"


def test_commit_script_stages_only_auditable_state_and_retries_push_once() -> None:
    script = COMMIT_SCRIPT.read_text()

    assert "git add -- data/ state/ alerts/" in script
    assert "git add ." not in script
    assert "git diff --cached --quiet" in script
    assert "git pull --rebase" in script
    assert script.count("git push") == 2
