# app.py
# Travel Dashboard — Shiny for Python entrypoint.
# Run from this directory:  shiny run app.py --reload

import threading

from shiny import App

from server import server
from ui import app_ui


def _warm_embeddings_background() -> None:
    try:
        from restaurant_rag import warm_embedding_model

        warm_embedding_model()
    except Exception:
        pass


threading.Thread(target=_warm_embeddings_background, daemon=True).start()

app = App(app_ui, server)
