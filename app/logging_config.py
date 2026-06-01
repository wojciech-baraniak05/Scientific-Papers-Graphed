import sys
from pathlib import Path

from loguru import logger

from app.config import get_settings

_CONFIGURED = False

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)


def configure_logging(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = (level or settings.log_level).upper()

    logger.remove()
    logger.add(sys.stderr, level=level, format=_FORMAT, enqueue=True, backtrace=False)

    try:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "ingest.log",
            level=level,
            format=_FORMAT,
            rotation="20 MB",
            retention="10 days",
            compression="zip",
            enqueue=True,
            backtrace=False,
        )
    except OSError as exc:
        logger.warning("File logging disabled ({}): {}", settings.log_dir, exc)

    _CONFIGURED = True
