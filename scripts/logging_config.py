import logging
from rich.logging import RichHandler

# --- Global Configuration ---
# level: Minimum severity to log
# format: Simplified because Rich handles the layout
# rich_tracebacks: Enables beautiful and detailed error formatting
LOGGER_CONFIG = {
    "level": logging.INFO,
    "format": "%(message)s",
    "datefmt": "[%X]",
    "rich_tracebacks": True,
    "markup": True, # Allows Rich markup (colors, bold) inside log messages
}



def get_logger(name: str = "core"):
    """
    Initializes and returns a singleton-like logger instance.
    Prevents duplicate handlers to avoid double logging in multi-module apps.
    """
    logger = logging.getLogger(name)
    
    # Global level setting
    logger.setLevel(LOGGER_CONFIG["level"])

    # Prevent handler duplication if get_logger is called multiple times
    if not logger.handlers:
        # Initialize RichHandler with advanced traceback support
        rich_handler = RichHandler(
            rich_tracebacks=LOGGER_CONFIG["rich_tracebacks"],
            markup=LOGGER_CONFIG["markup"]
        )
        
        # Apply formatting settings
        formatter = logging.Formatter(
            fmt=LOGGER_CONFIG["format"], 
            datefmt=LOGGER_CONFIG["datefmt"]
        )
        rich_handler.setFormatter(formatter)
        
        logger.addHandler(rich_handler)

    # Disable propagation to prevent parent (root) logger from double logging
    logger.propagate = False
    
    return logger
