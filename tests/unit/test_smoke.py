"""Smoke tests — validate the function app works end-to-end."""

import json
from unittest.mock import MagicMock

import azure.functions as func


def test_timer_trigger_completes() -> None:
    """Timer trigger executes through the full flow without error."""
    from semantic_folder.functions.timer_trigger import timer_trigger

    mock_timer = MagicMock(spec=func.TimerRequest)
    mock_timer.past_due = False

    timer_trigger(mock_timer)


def test_health_check_returns_status() -> None:
    """Health endpoint returns ok status with version from the package."""
    from semantic_folder.functions.http_trigger import health_check

    response = health_check(MagicMock(spec=func.HttpRequest))

    assert response.status_code == 200
    body = json.loads(response.get_body())
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
