from shiny import ui


def dining_dishes_output_ui():
    """Top row: dish recommendations only (Places live in a full-width row below)."""
    return ui.card(
        ui.card_header(
            ui.div(
                ui.span("Local Dishes to Try", class_="td-dining-card-title"),
                class_="td-dining-card-header",
            ),
        ),
        ui.div(ui.output_ui("out_dining_dishes"), class_="td-out-scroll"),
        class_="td-card td-out-card td-out-accent-dining td-dining-dishes-card",
        height="100%",
    )
