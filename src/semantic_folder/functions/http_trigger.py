"""HTTP trigger blueprint — health check and manual trigger endpoints."""

import json
import logging

import azure.functions as func

from semantic_folder import __version__
from semantic_folder.config import load_config
from semantic_folder.orchestration.processor import folder_processor_from_config

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


@bp.route(route="trigger", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def manual_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger endpoint — runs the delta processing pipeline on demand.

    Requires a function key for authentication. Executes the same logic
    as the timer trigger but returns results in the HTTP response.
    """
    logger.info("[manual_trigger] manual trigger requested")

    try:
        config = load_config()
        processor = folder_processor_from_config(config)
        listings = processor.process_delta()

        results = [
            {"folder_path": listing.folder_path, "file_count": len(listing.files)}
            for listing in listings
        ]
        for listing in listings:
            logger.info(
                "[manual_trigger] folder to regenerate; folder_path:%s;file_count:%d",
                listing.folder_path,
                len(listing.files),
            )
        logger.info("[manual_trigger] delta processing complete; folder_count:%d", len(listings))

        body = json.dumps({"status": "ok", "folders_processed": len(listings), "results": results})
        return func.HttpResponse(body, status_code=200, mimetype="application/json")

    except Exception:
        logger.error("[manual_trigger] manual trigger failed", exc_info=True)
        error_body = json.dumps({"status": "error", "message": "Internal server error"})
        return func.HttpResponse(error_body, status_code=500, mimetype="application/json")
