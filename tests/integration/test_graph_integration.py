"""Integration tests for Microsoft Graph API connectivity.

These tests require real Azure credentials and are skipped in CI/CD unless
the SF_CLIENT_ID environment variable is set.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("SF_CLIENT_ID"),
    reason="Real Graph credentials not available",
)


def test_fetch_delta_real() -> None:
    """Connect to the real Graph API and run a full delta cycle.

    Asserts that process_delta() returns a list (possibly empty on a clean
    run) without raising an exception.
    """
    from semantic_folder.config import load_config
    from semantic_folder.orchestration.processor import folder_processor_from_config

    config = load_config()
    processor = folder_processor_from_config(config)
    results = processor.process_delta()

    assert isinstance(results, list)
