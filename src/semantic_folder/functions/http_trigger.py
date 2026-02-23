"""HTTP trigger blueprint — health check and future webhook endpoint."""

import json
import logging

import azure.functions as func

from semantic_folder import __version__

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint.

    Returns service status and version. Will serve as the webhook
    endpoint for Graph notifications in a future iteration.
    """
    logger.info("[health_check] health check requested")

    try:
        body = json.dumps({"status": "ok", "version": __version__})
        return func.HttpResponse(body, status_code=200, mimetype="application/json")

    except Exception:
        logger.error("[health_check] health check failed", exc_info=True)
        error_body = json.dumps({"status": "error", "message": "Internal server error"})
        return func.HttpResponse(error_body, status_code=500, mimetype="application/json")
