from shiny import ui

from .trip_location_fields import compare_block


def compare_with_rows_content():
    """Compact compare rows without index column."""
    return compare_block()


def compare_with_rows_ui():
    return ui.card(
        ui.card_header("Compare with (optional)"),
        ui.p("Two rows · country + optional city each", class_="td-muted"),
        compare_block(),
        class_="td-card",
    )
