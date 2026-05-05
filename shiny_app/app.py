# app.py
# Travel Dashboard — Shiny for Python entrypoint.
# Local (repo root): `.venv\Scripts\python.exe -m shiny run shiny_app/app.py`
# Or: `cd shiny_app && ..\.venv\Scripts\python.exe -m shiny run app.py --reload`
# Running this file directly also starts the server (see __main__ below).

from pathlib import Path
import sys
import types

# Imports use the `shiny_app.*` package name in both layouts below.
_SHINY_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SHINY_APP_DIR.parent

# Repo checkout: `TravelDashboard/shiny_app/*.py` lives under a directory named `shiny_app`;
# add repo root so `import shiny_app` resolves to that folder.
# Posit Connect bundle: `rsconnect deploy shiny shiny_app` unpacks files at the app root
# (`app.py`, `server.py`, …) with no parent folder named `shiny_app` — register a namespace
# package so `shiny_app.server` still loads `server.py` next to `app.py`.
if (_REPO_ROOT / "shiny_app" / "server.py").is_file():
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
else:
    if str(_SHINY_APP_DIR) not in sys.path:
        sys.path.insert(0, str(_SHINY_APP_DIR))
    _pkg = types.ModuleType("shiny_app")
    _pkg.__path__ = [str(_SHINY_APP_DIR)]
    sys.modules["shiny_app"] = _pkg

import threading

from shiny import App

from shiny_app.server import server
from shiny_app.ui import app_ui

# Serve shiny_app/www at site root so client scripts can fetch /data/countries_slim.json.
_APP_DIR = _SHINY_APP_DIR

# Optional logging (console + file). Set TD_LOG_FILE=logs/app.log to enable file logging.
try:
    from shiny_app.logging_setup import configure_logging

    configure_logging(app_root=_SHINY_APP_DIR)
except Exception:
    pass


def _warm_embeddings_background() -> None:
    try:
        from shiny_app.restaurant_rag import warm_embedding_model

        warm_embedding_model()
    except Exception:
        pass


threading.Thread(target=_warm_embeddings_background, daemon=True).start()

app = App(app_ui, server, static_assets=_APP_DIR / "www")


if __name__ == "__main__":
    # IDE / `python shiny_app/app.py`: start ASGI server (same as `shiny run`).
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
