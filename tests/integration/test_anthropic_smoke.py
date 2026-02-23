"""Smoke test for Anthropic API integration.

Requires SF_ANTHROPIC_API_KEY to be set in the environment.
Run with: poetry run pytest tests/integration/test_anthropic_smoke.py -v -s
"""

from __future__ import annotations

import os

import pytest

from semantic_folder.description.describer import AnthropicDescriber

pytestmark = pytest.mark.skipif(
    "SF_ANTHROPIC_API_KEY" not in os.environ,
    reason="SF_ANTHROPIC_API_KEY not set",
)


@pytest.fixture
def describer() -> AnthropicDescriber:
    return AnthropicDescriber(api_key=os.environ["SF_ANTHROPIC_API_KEY"])


class TestSummarizeFile:
    def test_returns_nonempty_summary(self, describer: AnthropicDescriber) -> None:
        content = (
            b"# semantic-folder\n\n"
            b"AI-powered folder descriptions for OneDrive.\n"
            b"Uses Microsoft Graph API to detect changes and generate summaries.\n"
        )
        summary = describer.summarize_file("README.md", content)

        print(f"\n  File summary: {summary}")
        assert isinstance(summary, str)
        assert len(summary) > 10


class TestClassifyFolder:
    def test_returns_nonempty_classification(self, describer: AnthropicDescriber) -> None:
        folder_type = describer.classify_folder(
            "/drive/root:/Customers/Nexplore",
            ["SOW_2026_01.pdf", "invoice_2026_01.pdf", "meeting_notes.md"],
        )

        print(f"\n  Folder type: {folder_type}")
        assert isinstance(folder_type, str)
        assert len(folder_type) > 0
