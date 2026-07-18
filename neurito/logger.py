"""Logging central. Ejecución silenciosa: solo se registran errores, publicaciones
exitosas y alertas del sistema, con timestamp en hora de Colombia."""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from .config import config


class BogotaFormatter(logging.Formatter):
    """Formato legible y humano: fecha/hora de Colombia + ícono según importancia."""

    ICONS = {"DEBUG": "·", "INFO": "•", "WARNING": "⚠️", "ERROR": "⛔", "CRITICAL": "🚨"}

    def format(self, record):  # noqa: A003
        dt = datetime.fromtimestamp(record.created, config.timezone)
        icon = self.ICONS.get(record.levelname, "•")
        line = f"{dt.strftime('%d/%m  %H:%M:%S')}   {icon}  {record.getMessage()}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def get_logger(name: str = "neurito") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(BogotaFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = get_logger()
