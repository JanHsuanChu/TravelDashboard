from shiny import ui


def dining_dishes_output_ui():
    """Top row: dish recommendations only (Places live in a full-width row below)."""
    return ui.card(
        ui.card_header(
            ui.div(
                ui.span("Dining — dishes", class_="td-dining-card-title"),
                ui.span(ui.output_ui("dining_dest_badge"), class_="td-out-destination-tag-wrap"),
                class_="td-dining-card-header",
            ),
        ),
        ui.div(ui.output_ui("out_dining_dishes"), class_="td-out-scroll"),
        class_="td-card td-out-card td-out-accent-dining td-dining-dishes-card",
        height="100%",
    )
