from shiny import ui

import shiny_app.tags as tagdata


def when_fields_content():
    """When inputs only (no card)."""
    return ui.div(
        ui.p("When", class_="td-input-label td-trip-section-title"),
        ui.p("Season or month — pick one mode.", class_="td-muted td-input-hint"),
        ui.input_radio_buttons(
            "when_mode",
            None,
            {"season": "Season", "month": "Month"},
            selected="season",
            inline=True,
        ),
        ui.output_ui("when_timing_detail"),
        class_="td-input-group",
    )


def when_fields_ui():
    return ui.card(
        ui.card_header("When"),
        ui.p("Use either season or month — pick one mode below.", class_="td-muted"),
        ui.input_radio_buttons(
            "when_mode",
            None,
            {"season": "Season", "month": "Month"},
            selected="season",
            inline=True,
        ),
        ui.output_ui("when_timing_detail"),
        class_="td-card",
    )
