"""Timer trigger blueprint — scheduled entry point for folder description generation."""

import logging

import azure.functions as func

from semantic_folder.config import load_config
from semantic_folder.orchestration.processor import folder_processor_from_config

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def timer_trigger(timer: func.TimerRequest) -> None:
    """Scheduled trigger that processes OneDrive folder changes.

    Runs every 5 minutes. Detects changed OneDrive folders via the delta API
    and logs which folders need description regeneration.
    """
    logger.info("Timer trigger fired")

    try:
        if timer.past_due:
            logger.warning("Timer trigger is past due")

        config = load_config()
        processor = folder_processor_from_config(config)
        listings = processor.process_delta()
        for listing in listings:
            logger.info(
                "Folder to regenerate: %s (%d files)", listing.folder_path, len(listing.files)
            )
        logger.info("Delta processing complete — %d folder(s) need regeneration", len(listings))

    except Exception:
        logger.exception("Timer trigger failed")
        raise
