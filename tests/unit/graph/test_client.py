"""Unit tests for graph/client.py — MSAL auth and HTTP calls."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from semantic_folder.graph.client import GraphApiError, GraphAuthError, GraphClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> GraphClient:
    """Return a GraphClient with a mocked MSAL app."""
    with patch("semantic_folder.graph.client.msal.ConfidentialClientApplication"):
        client = GraphClient(
            client_id="test-client-id",
            client_secret="test-secret",
            tenant_id="test-tenant-id",
        )
    return client


def _mock_token_success(client: GraphClient) -> None:
    """Configure the MSAL mock to return a valid token."""
    client._app.acquire_token_for_client.return_value = {  # type: ignore[attr-defined]
        "access_token": "fake-token-abc"
    }


def _mock_token_failure(client: GraphClient) -> None:
    """Configure the MSAL mock to simulate token acquisition failure."""
    client._app.acquire_token_for_client.return_value = {  # type: ignore[attr-defined]
        "error": "invalid_client",
        "error_description": "Client secret is wrong",
    }


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


class TestGraphClientInit:
    def test_msal_app_created_with_correct_authority(self) -> None:
        with patch("semantic_folder.graph.client.msal.ConfidentialClientApplication") as mock_msal:
            GraphClient("cid", "csecret", "tid-001")
            mock_msal.assert_called_once_with(
                client_id="cid",
                client_credential="csecret",
                authority="https://login.microsoftonline.com/tid-001",
            )


# ---------------------------------------------------------------------------
# _acquire_token tests
# ---------------------------------------------------------------------------


class TestAcquireToken:
    def test_returns_token_on_success(self) -> None:
        client = _make_client()
        _mock_token_success(client)
        token = client._acquire_token()
        assert token == "fake-token-abc"

    def test_raises_auth_error_on_failure(self) -> None:
        client = _make_client()
        _mock_token_failure(client)
        with pytest.raises(GraphAuthError, match="invalid_client"):
            client._acquire_token()


# ---------------------------------------------------------------------------
# get() tests
# ---------------------------------------------------------------------------


class TestGraphClientGet:
    def test_get_constructs_correct_url_and_header(self) -> None:
        client = _make_client()
        _mock_token_success(client)

        response_data = {"value": [{"id": "item-1"}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("semantic_folder.graph.client.urllib_request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = mock_response
            result = client.get("/me/drive/root/delta")

        assert result == response_data
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.full_url == "https://graph.microsoft.com/v1.0/me/drive/root/delta"
        assert call_args.get_header("Authorization") == "Bearer fake-token-abc"

    def test_get_raises_graph_api_error_on_non_2xx(self) -> None:
        client = _make_client()
        _mock_token_success(client)

        error_body = json.dumps({"error": {"message": "Item not found"}}).encode()
        http_error = HTTPError(
            url="https://graph.microsoft.com/v1.0/me/drive/items/bad",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=BytesIO(error_body),
        )

        with (
            patch("semantic_folder.graph.client.urllib_request.urlopen", side_effect=http_error),
            pytest.raises(GraphApiError) as exc_info,
        ):
            client.get("/me/drive/items/bad")

        assert exc_info.value.status_code == 404
        assert "Item not found" in exc_info.value.message

    def test_get_raises_auth_error_when_token_fails(self) -> None:
        client = _make_client()
        _mock_token_failure(client)

        with pytest.raises(GraphAuthError):
            client.get("/me/drive/root/delta")

    def test_get_raises_graph_api_error_on_500(self) -> None:
        client = _make_client()
        _mock_token_success(client)

        http_error = HTTPError(
            url="https://graph.microsoft.com/v1.0/me/drive/root",
            code=500,
            msg="Internal Server Error",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=BytesIO(b"{}"),
        )

        with (
            patch("semantic_folder.graph.client.urllib_request.urlopen", side_effect=http_error),
            pytest.raises(GraphApiError) as exc_info,
        ):
            client.get("/me/drive/root")

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# put_content() tests
# ---------------------------------------------------------------------------


class TestGraphClientPutContent:
    def test_put_content_raises_not_implemented(self) -> None:
        client = _make_client()
        with pytest.raises(NotImplementedError):
            client.put_content("/me/drive/items/abc/content", b"# Hello", "text/markdown")

    def test_put_content_raises_not_implemented_with_default_content_type(self) -> None:
        client = _make_client()
        with pytest.raises(NotImplementedError):
            client.put_content("/me/drive/items/abc/content", b"data")


# ---------------------------------------------------------------------------
# GraphApiError tests
# ---------------------------------------------------------------------------


class TestGraphApiError:
    def test_status_code_and_message_stored(self) -> None:
        err = GraphApiError(403, "Access denied")
        assert err.status_code == 403
        assert err.message == "Access denied"

    def test_str_includes_status_code(self) -> None:
        err = GraphApiError(429, "Too many requests")
        assert "429" in str(err)
