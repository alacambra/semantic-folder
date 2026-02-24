"""AI description generation via Anthropic Messages API."""

from __future__ import annotations

import base64
import io
import logging
import time
from typing import TYPE_CHECKING

import anthropic
from anthropic.types import ImageBlockParam, Message, TextBlock, TextBlockParam
from anthropic.types.base64_image_source_param import Base64ImageSourceParam

if TYPE_CHECKING:
    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)

# Default content size limit per file
DEFAULT_MAX_FILE_CONTENT_BYTES = 8192

# Rate-limit defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUEST_DELAY = 1.0

# File extensions that require special handling
_DOCX_EXTENSIONS = frozenset({".docx"})
_PDF_EXTENSIONS = frozenset({".pdf"})
_IMAGE_EXTENSIONS: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


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


def _file_extension(filename: str) -> str:
    """Return the lowercased file extension including the dot."""
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _extract_docx_text(content: bytes) -> str:
    """Extract plain text from a .docx file.

    Args:
        content: Raw bytes of the .docx file.

    Returns:
        Extracted text, or a fallback marker if extraction fails.
    """
    try:
        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        logger.warning("[_extract_docx_text] failed to extract text from .docx")
        return ""


class AnthropicDescriber:
    """Generates file summaries and folder classifications using Claude."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        max_file_content_bytes: int = DEFAULT_MAX_FILE_CONTENT_BYTES,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ) -> None:
        """Initialise the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model identifier to use for generation.
            max_file_content_bytes: Max bytes to read per file for summarization.
            max_retries: Max retry attempts for rate-limited requests (SDK built-in).
            request_delay: Seconds to sleep before each API call to throttle throughput.
        """
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=max_retries)
        self._model = model
        self._max_file_content_bytes = max_file_content_bytes
        self._request_delay = request_delay

    def summarize_file(self, filename: str, content: bytes) -> str:
        """Generate a one-line summary of a file.

        Dispatches to the appropriate strategy based on file extension:
        - ``.docx``: extracts plain text via python-docx, sends as text.
        - ``.pdf``: sends as a base64-encoded PDF document content block.
        - Images (``.png``, ``.jpg``, ``.jpeg``, ``.gif``, ``.webp``): sends as
          a base64-encoded image content block.
        - Everything else: decodes as UTF-8 text (with replacement).

        Args:
            filename: Name of the file.
            content: Raw file content.

        Returns:
            A brief summary string.
        """
        ext = _file_extension(filename)

        if ext in _DOCX_EXTENSIONS:
            return self._summarize_docx(filename, content)
        if ext in _PDF_EXTENSIONS:
            return self._summarize_pdf(filename, content)
        if ext in _IMAGE_EXTENSIONS:
            return self._summarize_image(filename, content, _IMAGE_EXTENSIONS[ext])
        return self._summarize_text(filename, content)

    def _summarize_text(self, filename: str, content: bytes) -> str:
        """Summarize a text-decodable file."""
        truncated = content[: self._max_file_content_bytes]
        try:
            text_content = truncated.decode("utf-8", errors="replace")
        except Exception:
            text_content = f"[binary file: {filename}]"

        prompt = (
            f"Summarize this file in one sentence. "
            f"File name: {filename}\n\n"
            f"Content:\n{text_content}"
        )
        logger.info(
            "[summarize_file] sending text prompt; filename:%s;content_bytes:%d",
            filename,
            len(truncated),
        )
        if self._request_delay > 0:
            time.sleep(self._request_delay)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_text(message)
        logger.info(
            "[summarize_file] received response; filename:%s;summary:%s",
            filename,
            result,
        )
        return result

    def _summarize_docx(self, filename: str, content: bytes) -> str:
        """Summarize a .docx file by extracting its text first."""
        extracted = _extract_docx_text(content)
        if not extracted:
            logger.warning("[summarize_file] docx text extraction empty; filename:%s", filename)
            extracted = f"[could not extract text from {filename}]"

        truncated = extracted[: self._max_file_content_bytes]
        prompt = (
            f"Summarize this file in one sentence. File name: {filename}\n\nContent:\n{truncated}"
        )
        logger.info(
            "[summarize_file] sending docx prompt; filename:%s;chars:%d",
            filename,
            len(truncated),
        )
        if self._request_delay > 0:
            time.sleep(self._request_delay)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_text(message)
        logger.info(
            "[summarize_file] received response; filename:%s;summary:%s",
            filename,
            result,
        )
        return result

    def _summarize_pdf(self, filename: str, content: bytes) -> str:
        """Summarize a PDF file using the native document content block."""
        encoded = base64.standard_b64encode(content).decode("ascii")
        logger.info(
            "[summarize_file] sending pdf document block; filename:%s;raw_bytes:%d",
            filename,
            len(content),
        )
        if self._request_delay > 0:
            time.sleep(self._request_delay)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": (f"Summarize this file in one sentence. File name: {filename}"),
                        },
                    ],
                }
            ],
        )
        result = _extract_text(message)
        logger.info(
            "[summarize_file] received response; filename:%s;summary:%s",
            filename,
            result,
        )
        return result

    def _summarize_image(self, filename: str, content: bytes, media_type: str) -> str:
        """Summarize an image file using a base64-encoded image content block."""
        encoded = base64.standard_b64encode(content).decode("ascii")
        logger.info(
            "[summarize_file] sending image block; filename:%s;raw_bytes:%d",
            filename,
            len(content),
        )
        if self._request_delay > 0:
            time.sleep(self._request_delay)
        image_block = ImageBlockParam(
            type="image",
            source=Base64ImageSourceParam(
                type="base64",
                media_type=media_type,  # pyright: ignore[reportArgumentType]
                data=encoded,
            ),
        )
        text_block = TextBlockParam(
            type="text",
            text=f"Summarize this file in one sentence. File name: {filename}",
        )
        message = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[{"role": "user", "content": [image_block, text_block]}],
        )
        result = _extract_text(message)
        logger.info(
            "[summarize_file] received response; filename:%s;summary:%s",
            filename,
            result,
        )
        return result

    def classify_folder(self, folder_path: str, filenames: list[str]) -> str:
        """Classify a folder into a category based on its path and contents.

        Args:
            folder_path: OneDrive path of the folder.
            filenames: List of file names in the folder.

        Returns:
            A short folder type classification (e.g. "project-docs", "invoices").
        """
        file_list = "\n".join(f"- {f}" for f in filenames)
        prompt = (
            f"Classify this folder into a short category label "
            f"(1-2 words, lowercase, hyphenated). "
            f"Folder path: {folder_path}\n"
            f"Files:\n{file_list}"
        )
        logger.info(
            "[classify_folder] sending prompt; folder:%s;file_count:%d",
            folder_path,
            len(filenames),
        )
        if self._request_delay > 0:
            time.sleep(self._request_delay)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_text(message).strip()
        logger.debug(
            "[classify_folder] received response; folder:%s;classification:%s",
            folder_path,
            result,
        )
        return result


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
        max_file_content_bytes=config.max_file_content_bytes,
        max_retries=config.anthropic_max_retries,
        request_delay=config.anthropic_request_delay,
    )
