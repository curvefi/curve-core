import logging

from rich.logging import RichHandler

LOGGER_CONFIG = {
    "level": logging.INFO,
    "format": "%(message)s",
    "datefmt": "[%X]",
    "handlers": [RichHandler(rich_tracebacks=True)],
}


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(LOGGER_CONFIG["level"])

    if not logger.handlers:
        handler = LOGGER_CONFIG["handlers"][0]
        handler.setFormatter(logging.Formatter(LOGGER_CONFIG["format"], LOGGER_CONFIG["datefmt"]))
        logger.addHandler(handler)

    return logger
