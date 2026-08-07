import logging
import sys

# Define a constant for the logger name to make it easy to call from other modules
LOGGER_NAME = "MyApp"
LOG_LEVEL = logging.INFO
# Define a standard ISO 8601-like format for the timestamp
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logger() -> logging.Logger:
    """
    Initializes and configures a dedicated application logger.
    
    The logger is configured to output messages to the console (sys.stderr by default) 
    with a specific format and level.
    
    Returns:
        logging.Logger: The configured application logger instance.
    """
    
    # Use a named logger instead of the root logger for better modularity.
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(LOG_LEVEL)

    # Prevent logs from propagating to the root logger handlers, 
    # ensuring only our specific configuration is used.
    logger.propagate = False

    # Check if a handler is already attached to prevent duplicate log messages.
    if not logger.handlers:
        # StreamHandler defaults to sys.stderr, which is standard practice for logging, 
        # especially for errors/warnings.
        handler = logging.StreamHandler(sys.stdout) # Keeping sys.stdout as requested by original code
        handler.setLevel(LOG_LEVEL)
        
        # Create the formatter
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        handler.setFormatter(formatter)
        
        # Add the handler to the logger
        logger.addHandler(handler)

    # Return the configured logger instance
    return logger

# Example of usage (optional, but shows how to initialize and use the logger)
if __name__ == "__main__":
    my_logger = setup_logger()
    my_logger.info("Logger setup successful and initialized.")
    my_logger.warning("This is a warning message.")
    my_logger.debug("This debug message will not appear because the level is INFO.")
