from shiny import ui

from .trip_location_fields import destination_block


def destination_fields_content():
    """Inputs only (no card) — for Plan Your Trip grid."""
    return destination_block()


def destination_fields_ui():
    return ui.card(
        ui.card_header("Where I am going"),
        ui.p("Country required · city optional", class_="td-muted"),
        destination_block(),
        class_="td-card",
    )
