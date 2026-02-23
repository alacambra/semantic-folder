"""Smoke tests — validate the function app works end-to-end."""

import json
from unittest.mock import MagicMock, patch

import azure.functions as func

from semantic_folder.graph.models import FolderListing


def test_timer_trigger_completes() -> None:
    """Timer trigger executes through the full flow without error."""
    from semantic_folder.functions.timer_trigger import timer_trigger

    mock_timer = MagicMock(spec=func.TimerRequest)
    mock_timer.past_due = False

    mock_processor = MagicMock()
    mock_processor.process_delta.return_value = [
        FolderListing(folder_id="f1", folder_path="/drive/root:/Docs", files=["a.txt"]),
    ]

    with (
        patch("semantic_folder.functions.timer_trigger.load_config"),
        patch(
            "semantic_folder.functions.timer_trigger.folder_processor_from_config",
            return_value=mock_processor,
        ),
    ):
        timer_trigger(mock_timer)

    mock_processor.process_delta.assert_called_once()


def test_health_check_returns_status() -> None:
    """Health endpoint returns ok status with version from the package."""
    from semantic_folder.functions.http_trigger import health_check

    response = health_check(MagicMock(spec=func.HttpRequest))

    assert response.status_code == 200
    body = json.loads(response.get_body())
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
