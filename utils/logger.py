# utils/logger.py

# logger负责打印出日志，包括调试信息、警告、错误等

import logging
from rich.logging import RichHandler
import os
from datetime import datetime

def setup_logger():
    """Configures the logger for the application."""
    
    # Create debug directory if it doesn't exist
    debug_dir = "debug"
    os.makedirs(debug_dir, exist_ok=True)

    # Define log file path with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(debug_dir, f"app_{timestamp}.log")

    # Configure basic logging for file output
    logging.basicConfig(
        level="DEBUG",  # Capture all levels for file
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="[%Y-%m-%d %H:%M:%S]",
        handlers=[
            RichHandler(rich_tracebacks=True, level="INFO"), # Console output level
            logging.FileHandler(log_file_path, encoding='utf-8') # File output
        ]
    )
    
    # Get the logger instance
    logger = logging.getLogger("rich")
    
    # Set the logger's level to DEBUG to ensure all messages are processed by handlers
    logger.setLevel(logging.DEBUG)
    
    return logger

log = setup_logger()