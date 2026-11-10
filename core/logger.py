"""日志模块：统一日志配置"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_logger(name: str = "math_obsidian_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_dir = Path(os.environ.get("MATH_OBSIDIAN_HOME", str(Path.home() / ".math_obsidian_agent"))) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 文件日志（轮转）
    fh = RotatingFileHandler(
        log_dir / "agent.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)

    # 控制台日志
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    if ch.stream is not None:
        logger.addHandler(ch)

    return logger
