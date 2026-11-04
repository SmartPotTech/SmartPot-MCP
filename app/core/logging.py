"""Server logger. Writes to stderr: in stdio mode, stdout is reserved for the MCP protocol stream."""

import logging
import sys


def setup_logger(name: str = "smartpot-mcp", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
        )
        logger.addHandler(handler)
    # Sin propagar: evita líneas duplicadas cuando uvicorn configura el logger raíz.
    logger.propagate = False
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


logger = setup_logger()
