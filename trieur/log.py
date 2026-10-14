"""Journal technique (trieur.log) : étapes, durées et erreurs, pour comprendre un problème."""
from __future__ import annotations

import logging
import platform
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .settings import cache_dir

logger = logging.getLogger("trieur")


def log_file() -> Path:
    return cache_dir() / "trieur.log"


def setup():
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(log_file(), maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    from . import __version__
    logger.info("=== Trieur de photos %s · Python %s · %s", __version__, platform.python_version(), platform.platform())


def error_text(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def install_excepthook(show):
    """Toute erreur non prévue est inscrite au journal et affichée (sinon, sans console, elle passerait inaperçue)."""
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logger.error("Erreur non prévue :\n%s", text)
        try:
            show(f"{exc_type.__name__} : {exc}", text)
        except Exception:
            pass
    sys.excepthook = hook
