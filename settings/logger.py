import logging
import sys
from typing import Optional


def setup_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a basic logger for the application or a specific module.

    This function ensures that a StreamHandler is only added once and directs
    log output to sys.stderr for better separation from normal program output.

    Args:
        name: The name of the logger to configure (e.g., 'app.module'). 
              If None, configures the root logger.
        level: The minimum logging level to output.

    Returns:
        The configured logging.Logger instance.
    """
    # 1. Get the logger instance.
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 2. Check if a StreamHandler is already present to prevent duplicate logs.
    if not logger.handlers:
        # Create a StreamHandler that directs logs to standard error.
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        
        # Define a consistent format for log messages.
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        
        # Add the handler to the logger.
        logger.addHandler(handler)
    
    return logger

# Example Usage (Not part of the optimized function, for illustration only):
if __name__ == "__main__":
    # Configure the root logger
    root_log = setup_logger()
    root_log.info("This is an INFO message from the root logger.")
    
    # Configure a specific module logger
    module_log = setup_logger("database_module", logging.DEBUG)
    module_log.debug("This is a DEBUG message from the module logger.")
    module_log.error("This is an ERROR message from the module logger.")
