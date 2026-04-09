# app.py
# Travel Dashboard — Shiny for Python entrypoint.
# Run from this directory:  shiny run app.py --reload

from shiny import App

from server import server
from ui import app_ui

app = App(app_ui, server)
