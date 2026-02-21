"""Timer trigger blueprint — scheduled entry point for folder description generation."""

import logging

import azure.functions as func

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def timer_trigger(timer: func.TimerRequest) -> None:
    """Scheduled trigger that processes OneDrive folder changes.

    Runs every 5 minutes. Currently a placeholder — Graph delta processing
    will be implemented in iteration 2.
    """
    logger.info("Timer trigger fired")

    try:
        if timer.past_due:
            logger.warning("Timer trigger is past due")

        # Placeholder: Graph delta processing goes here (iteration 2)
        logger.info("Timer trigger completed successfully")

    except Exception:
        logger.exception("Timer trigger failed")
        raise
