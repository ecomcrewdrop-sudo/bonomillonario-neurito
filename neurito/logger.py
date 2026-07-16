"""Logging central. Ejecución silenciosa: solo se registran errores, publicaciones
exitosas y alertas del sistema, con timestamp en hora de Colombia."""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from .config import config


class BogotaFormatter(logging.Formatter):
    """Formatea los timestamps en la zona horaria de Colombia."""

    def formatTime(self, record, datefmt=None):  # noqa: N802
        dt = datetime.fromtimestamp(record.created, config.timezone)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


def get_logger(name: str = "neurito") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        BogotaFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %Z",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = get_logger()
