# utils/logger.py

# logger负责打印出日志，包括调试信息、警告、错误等

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