"""Unit tests for description/describer.py — AnthropicDescriber behaviour."""

from unittest.mock import MagicMock, patch

from anthropic.types import Message, TextBlock, Usage

from semantic_folder.description.describer import (
    MAX_FILE_CONTENT_BYTES,
    AnthropicDescriber,
    anthropic_describer_from_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_describer() -> tuple[AnthropicDescriber, MagicMock]:
    """Return (describer, mock_anthropic_client)."""
    with patch("semantic_folder.description.describer.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        describer = AnthropicDescriber(api_key="test-key", model="test-model")
    return describer, mock_client


def _mock_message_response(text: str) -> Message:
    """Create an Anthropic Message response with the given text."""
    return Message(
        id="msg-test",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
        model="test-model",
        stop_reason="end_turn",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestAnthropicDescriberInit:
    def test_creates_client_with_api_key(self) -> None:
        with patch("semantic_folder.description.describer.anthropic.Anthropic") as mock_cls:
            AnthropicDescriber(api_key="sk-test-123", model="claude-haiku-4-5-20251001")
            mock_cls.assert_called_once_with(api_key="sk-test-123")

    def test_stores_model(self) -> None:
        describer, _ = _make_describer()
        assert describer._model == "test-model"


# ---------------------------------------------------------------------------
# summarize_file tests
# ---------------------------------------------------------------------------


class TestSummarizeFile:
    def test_calls_messages_create_with_correct_params(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("A test summary.")

        describer.summarize_file("report.pdf", b"file content here")

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["max_tokens"] == 150
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "report.pdf" in messages[0]["content"]
        assert "file content here" in messages[0]["content"]

    def test_truncates_content_to_max_bytes(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("Summary.")

        large_content = b"x" * (MAX_FILE_CONTENT_BYTES + 5000)
        describer.summarize_file("big.txt", large_content)

        call_kwargs = mock_client.messages.create.call_args[1]
        prompt_content = call_kwargs["messages"][0]["content"]
        # The prompt should contain at most MAX_FILE_CONTENT_BYTES worth of 'x'
        assert "x" * MAX_FILE_CONTENT_BYTES in prompt_content
        assert "x" * (MAX_FILE_CONTENT_BYTES + 1) not in prompt_content

    def test_handles_binary_content_with_replace(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("Binary file.")

        binary_content = bytes(range(256))
        describer.summarize_file("image.bin", binary_content)

        call_kwargs = mock_client.messages.create.call_args[1]
        prompt_content = call_kwargs["messages"][0]["content"]
        # Should not raise — binary decoded with errors="replace"
        assert "image.bin" in prompt_content

    def test_returns_text_from_first_content_block(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response(
            "This is a quarterly report."
        )

        result = describer.summarize_file("report.pdf", b"Q1 results...")

        assert result == "This is a quarterly report."

    def test_empty_content_produces_valid_prompt(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("Empty file.")

        result = describer.summarize_file("empty.txt", b"")

        assert result == "Empty file."
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# classify_folder tests
# ---------------------------------------------------------------------------


class TestClassifyFolder:
    def test_calls_messages_create_with_folder_path_and_files(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("project-docs")

        describer.classify_folder("/drive/root:/Projects", ["readme.md", "plan.docx"])

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["max_tokens"] == 50
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert "/drive/root:/Projects" in messages[0]["content"]
        assert "- readme.md" in messages[0]["content"]
        assert "- plan.docx" in messages[0]["content"]

    def test_returns_stripped_text(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("  invoices  \n")

        result = describer.classify_folder("/path", ["invoice.pdf"])

        assert result == "invoices"

    def test_empty_filenames_list(self) -> None:
        describer, mock_client = _make_describer()
        mock_client.messages.create.return_value = _mock_message_response("empty-folder")

        result = describer.classify_folder("/path", [])

        assert result == "empty-folder"
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# anthropic_describer_from_config tests
# ---------------------------------------------------------------------------


class TestAnthropicDescriberFromConfig:
    def test_passes_api_key_and_model_from_config(self) -> None:
        config = MagicMock()
        config.anthropic_api_key = "sk-from-config"
        config.anthropic_model = "claude-haiku-4-5-20251001"

        with patch("semantic_folder.description.describer.anthropic.Anthropic") as mock_cls:
            describer = anthropic_describer_from_config(config)

        mock_cls.assert_called_once_with(api_key="sk-from-config")
        assert describer._model == "claude-haiku-4-5-20251001"
