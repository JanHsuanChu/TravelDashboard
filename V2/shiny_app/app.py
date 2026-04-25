# app.py
# Travel Dashboard — Shiny for Python entrypoint.
# Local: from repo root `shiny run shiny_app/app.py` or `cd shiny_app && shiny run app.py --reload`

from pathlib import Path
import sys

# Posit Connect loads `shiny_app.app:app` with TravelDashboard root on sys.path.
# `cd shiny_app && shiny run app.py` only puts shiny_app/ on path — add parent so `shiny_app.*` resolves.
_SHINY_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SHINY_APP_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import threading

from shiny import App

from shiny_app.server import server
from shiny_app.ui import app_ui

# Serve shiny_app/www at site root so client scripts can fetch /data/countries_slim.json.
_APP_DIR = _SHINY_APP_DIR


def _warm_embeddings_background() -> None:
    try:
        from shiny_app.restaurant_rag import warm_embedding_model

        warm_embedding_model()
    except Exception:
        pass


threading.Thread(target=_warm_embeddings_background, daemon=True).start()

app = App(app_ui, server, static_assets=_APP_DIR / "www")
