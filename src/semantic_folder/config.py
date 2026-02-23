"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Centralized application configuration.

    Required fields have no defaults and will cause a KeyError at startup
    if the corresponding environment variable is missing. Domain constants
    have sensible defaults but can be overridden via environment variables.
    """

    # Required — no defaults, fail at startup if missing
    client_id: str
    client_secret: str
    tenant_id: str
    drive_user: str
    storage_connection_string: str
    anthropic_api_key: str

    # Domain constants — defaults provided, overridable via env
    delta_container: str = "semantic-folder-state"
    delta_blob: str = "delta-token/current.txt"
    folder_description_filename: str = "folder_description.md"
    anthropic_model: str = "claude-haiku-4-5-20251001"
    max_file_content_bytes: int = 8192


def load_config() -> AppConfig:
    """Construct an AppConfig from environment variables.

    Required environment variables:
        SF_CLIENT_ID: Azure AD application (client) ID.
        SF_CLIENT_SECRET: Azure AD application client secret.
        SF_TENANT_ID: Azure AD tenant ID.
        SF_DRIVE_USER: UPN or object ID of the OneDrive user to poll.
        AzureWebJobsStorage: Azure Storage account connection string.
        SF_ANTHROPIC_API_KEY: Anthropic API key for AI description generation.

    Optional environment variables (with defaults):
        SF_DELTA_CONTAINER: Blob container for delta token storage.
        SF_DELTA_BLOB: Blob path for the delta token file.
        SF_FOLDER_DESCRIPTION_FILENAME: Name of the generated description file.
        SF_ANTHROPIC_MODEL: Anthropic model identifier (default: claude-haiku-4-5-20251001).
        SF_MAX_FILE_CONTENT_BYTES: Max bytes to read per file for AI summarization (default: 8192).

    Returns:
        Configured AppConfig instance.
    """
    return AppConfig(
        client_id=os.environ["SF_CLIENT_ID"],
        client_secret=os.environ["SF_CLIENT_SECRET"],
        tenant_id=os.environ["SF_TENANT_ID"],
        drive_user=os.environ["SF_DRIVE_USER"],
        storage_connection_string=os.environ["AzureWebJobsStorage"],  # noqa: SIM112
        anthropic_api_key=os.environ["SF_ANTHROPIC_API_KEY"],
        delta_container=os.environ.get("SF_DELTA_CONTAINER", "semantic-folder-state"),
        delta_blob=os.environ.get("SF_DELTA_BLOB", "delta-token/current.txt"),
        folder_description_filename=os.environ.get(
            "SF_FOLDER_DESCRIPTION_FILENAME", "folder_description.md"
        ),
        anthropic_model=os.environ.get("SF_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        max_file_content_bytes=int(os.environ.get("SF_MAX_FILE_CONTENT_BYTES", "8192")),
    )
