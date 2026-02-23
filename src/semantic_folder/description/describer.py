"""AI description generation via Anthropic Messages API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import anthropic
from anthropic.types import Message, TextBlock

if TYPE_CHECKING:
    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)

# Content size limit per file (first 8 KB)
MAX_FILE_CONTENT_BYTES = 8192


def _extract_text(message: Message) -> str:
    """Extract the text from the first TextBlock in a message response.

    Args:
        message: Anthropic Message response.

    Returns:
        Text content from the first TextBlock.

    Raises:
        ValueError: If no TextBlock is found in the response.
    """
    for block in message.content:
        if isinstance(block, TextBlock):
            return block.text
    raise ValueError("No TextBlock found in Anthropic response")


class AnthropicDescriber:
    """Generates file summaries and folder classifications using Claude."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        """Initialise the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model identifier to use for generation.
        """
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def summarize_file(self, filename: str, content: bytes) -> str:
        """Generate a one-line summary of a file.

        Args:
            filename: Name of the file.
            content: Raw file content (truncated to MAX_FILE_CONTENT_BYTES).

        Returns:
            A brief summary string.
        """
        truncated = content[:MAX_FILE_CONTENT_BYTES]
        try:
            text_content = truncated.decode("utf-8", errors="replace")
        except Exception:
            text_content = f"[binary file: {filename}]"

        message = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Summarize this file in one sentence. "
                        f"File name: {filename}\n\n"
                        f"Content:\n{text_content}"
                    ),
                }
            ],
        )
        return _extract_text(message)

    def classify_folder(self, folder_path: str, filenames: list[str]) -> str:
        """Classify a folder into a category based on its path and contents.

        Args:
            folder_path: OneDrive path of the folder.
            filenames: List of file names in the folder.

        Returns:
            A short folder type classification (e.g. "project-docs", "invoices").
        """
        file_list = "\n".join(f"- {f}" for f in filenames)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=50,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Classify this folder into a short category label "
                        f"(1-2 words, lowercase, hyphenated). "
                        f"Folder path: {folder_path}\n"
                        f"Files:\n{file_list}"
                    ),
                }
            ],
        )
        return _extract_text(message).strip()


def anthropic_describer_from_config(config: AppConfig) -> AnthropicDescriber:
    """Construct an AnthropicDescriber from application configuration.

    Args:
        config: Application configuration instance.

    Returns:
        Configured AnthropicDescriber instance.
    """
    return AnthropicDescriber(
        api_key=config.anthropic_api_key,
        model=config.anthropic_model,
    )
