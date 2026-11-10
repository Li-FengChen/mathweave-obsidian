"""Resolve read-only resources for source and portable builds."""
import sys
from pathlib import Path

APP_NAME = "数学知识织网"
APP_VERSION = "2.2.1"


def resource_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / relative
