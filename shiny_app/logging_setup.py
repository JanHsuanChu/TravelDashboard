from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _truthy(v: str | None) -> bool:
    s = (v or "").strip().strip('"').strip("'").lower()
    return s in ("1", "true", "yes", "on")


def configure_logging(*, app_root: Path) -> None:
    """
    Configure console logging plus optional rotating file logging.

    Env vars:
    - TD_LOG_LEVEL=INFO|DEBUG|WARNING|ERROR (default INFO)
    - TD_LOG_FILE=0/off/false to disable file logging (default console-only)
      or a relative/absolute path to enable (default when set: logs/app.log under shiny_app/)
    """
    level_name = (os.environ.get("TD_LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        h = logging.StreamHandler()
        h.setLevel(level)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)

    raw_file = (os.environ.get("TD_LOG_FILE") or "").strip()
    if raw_file.lower() in ("0", "off", "false", "no"):
        return
    if not raw_file:
        return

    p = Path(raw_file)
    if not p.is_absolute():
        p = (app_root / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    fh = RotatingFileHandler(str(p), maxBytes=800_000, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)

