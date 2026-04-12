from shiny import ui


def dining_places_map_output_ui():
    """Full-width row: recommended places list + Google Map."""
    return ui.card(
        ui.card_header(
            ui.span("Dining — recommended places", class_="td-dining-places-card-title"),
        ),
        ui.div(ui.output_ui("places_retrieval_error"), class_="td-places-error-host"),
        ui.div(
            ui.input_text("map_place_pick", "", value="0"),
            class_="td-hidden-shiny-input-wrap",
        ),
        ui.div(
            ui.layout_columns(
                ui.div(ui.output_ui("out_dining_places_list"), class_="td-dining-places-list-wrap"),
                ui.div(ui.output_ui("out_dining_places_map"), class_="td-dining-places-map-wrap"),
                col_widths=(5, 7),
                gap="1.25rem",
            ),
            class_="td-dining-places-split",
        ),
        class_="td-card td-out-card td-out-accent-dining td-dining-places-card",
    )
