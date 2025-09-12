# utils/logger.py
import logging
from rich.logging import RichHandler

def setup_logger():
    """Configures the logger for the application."""
    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    return logging.getLogger("rich")

log = setup_logger()
