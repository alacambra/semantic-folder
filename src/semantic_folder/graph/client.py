"""Microsoft Graph API client with MSAL authentication."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from urllib import request as urllib_request
from urllib.error import HTTPError

import msal

if TYPE_CHECKING:
    from semantic_folder.config import AppConfig

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]
AUTHORITY_BASE_URL = "https://login.microsoftonline.com"


class GraphAuthError(Exception):
    """Raised when MSAL token acquisition fails."""


class GraphApiError(Exception):
    """Raised when the Graph API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Graph API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class GraphClient:
    """Authenticated client for Microsoft Graph API."""

    def __init__(self, client_id: str, client_secret: str, tenant_id: str) -> None:
        """Initialise the MSAL confidential client application.

        Args:
            client_id: Azure AD application (client) ID.
            client_secret: Azure AD application client secret.
            tenant_id: Azure AD tenant ID.
        """
        authority = f"{AUTHORITY_BASE_URL}/{tenant_id}"
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )

    def _acquire_token(self) -> str:
        """Acquire a Bearer token using client credentials flow.

        Returns:
            Access token string.

        Raises:
            GraphAuthError: If MSAL cannot acquire a token.
        """
        result: dict[str, Any] = self._app.acquire_token_for_client(scopes=GRAPH_SCOPES) or {}
        if "access_token" not in result:
            error = result.get("error", "unknown_error")
            description = result.get("error_description", "No description provided")
            logger.error("[_acquire_token] MSAL token acquisition failed; error:%s", error)
            raise GraphAuthError(f"Token acquisition failed: {error} — {description}")
        return str(result["access_token"])

    def get(self, path: str) -> dict[str, Any]:
        """Perform an authenticated GET request to the Graph API.

        Args:
            path: URL path relative to BASE_URL (must start with '/').

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            GraphAuthError: If token acquisition fails.
            GraphApiError: If the API returns a non-2xx status code.
        """
        token = self._acquire_token()
        url = f"{GRAPH_BASE_URL}{path}"
        req = urllib_request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib_request.urlopen(req) as resp:
                body = resp.read()
                return json.loads(body)  # type: ignore[no-any-return]
        except HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw).get("error", {}).get("message", exc.reason)
            except Exception:
                detail = exc.reason
            raise GraphApiError(exc.code, detail) from exc

    def put_content(
        self,
        path: str,
        content: bytes,
        content_type: str = "text/markdown",
    ) -> None:
        """Perform an authenticated PUT request to upload content to the Graph API.

        This method is a stub for IT-4. It will be implemented when folder
        description upload is required.

        Args:
            path: URL path relative to BASE_URL (must start with '/').
            content: Raw bytes to upload.
            content_type: MIME type for the Content-Type header.

        Raises:
            NotImplementedError: Always — stub pending IT-4 implementation.
        """
        raise NotImplementedError("put_content will be implemented in IT-4")


def graph_client_from_config(config: AppConfig) -> GraphClient:
    """Construct a GraphClient from application configuration.

    Args:
        config: Application configuration instance.

    Returns:
        Configured GraphClient instance.
    """
    return GraphClient(
        client_id=config.client_id,
        client_secret=config.client_secret,
        tenant_id=config.tenant_id,
    )
